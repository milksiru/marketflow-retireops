# marketflow-retireops

MarketFlow RetireOps is a market briefing and DC retirement-plan reference service.

It is wired for the workstation Kubernetes delivery flow:

Pushes to `main` are built by the workstation self-hosted runner and deployed through Argo CD.

```text
push to main
-> GitHub Actions self-hosted runner on workstation
-> podman build
-> 192.168.55.148:5000/milksiru/marketflow-retireops:<git-sha>
-> deploy/k8s/deployment.yaml update
-> Argo CD sync
-> Kubernetes rollout
```

## Features

- Dashboard with market mood cards, index strip, watchlist, DC retirement card, and alert preview
- Mobile-first consumer finance UI with Home, Reports, Notifications, and Settings views
- Live market polling through the Yahoo Finance chart endpoint with a 25 second backend cache and 30 second dashboard refresh
- Daily report previews for SMS and Kakao-style button messages
- Report subscription API for channel, recipient, send time, and timezone management
- Notification API:
  - `GET /api/notifications`
  - `GET /api/notifications/stats`
  - `GET /api/notifications/channels`
  - `POST /api/notifications/test`
  - `POST /api/notifications/send`
  - `PUT /api/notifications/channels/{channel}/settings`
  - `GET /api/subscriptions`
  - `POST /api/subscriptions`
- Provider interface for Email, SMS, Kakao, Telegram, and Microsoft Teams
- Email, Teams, and Telegram providers are implemented with real send hooks
- SMS and Kakao providers are mock providers with integration-ready config
- SQLite log tables for notification channels, logs, and report subscriptions
- Kubernetes CronJobs for Morning, Market Open, Evening, Weekly, and Monthly DC reports

## Secrets

Sensitive values are injected only through Kubernetes Secrets:

```text
EMAIL_SMTP_HOST
EMAIL_SMTP_PORT
EMAIL_SMTP_USER
EMAIL_SMTP_PASSWORD
TEAMS_WEBHOOK_URL
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
SMS_PROVIDER
SMS_ACCESS_KEY
SMS_SECRET_KEY
SMS_SENDER_NUMBER
KAKAO_PROVIDER
KAKAO_API_KEY
KAKAO_SENDER_KEY
KAKAO_TEMPLATE_CODE
```

Update them on workstation:

```bash
kubectl -n apps edit secret marketflow-retireops-secrets
```

Channel settings are managed through:

```bash
curl -X PUT http://192.168.55.42:31081/api/notifications/channels/telegram/settings \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true,"provider":"bot","config":{}}'
```

Secrets stay in Kubernetes Secret only. Provider config in the DB is for non-sensitive routing options.

## Local API

```bash
python -m app.server
```

## Cron Schedules

All schedules use `Asia/Seoul`.

```text
Morning Brief:      30 7 * * 1-5
Market Open Watch:  50 8 * * 1-5
Evening Brief:      30 18 * * 1-5
Weekly Report:      0 9 * * 6
Monthly DC Report:  0 9 1 * *
```

## Operations

Market data behavior:

- `/api/dashboard` fetches the latest available quote data when the backend cache expires.
- Backend cache TTL is 25 seconds.
- The web dashboard refreshes market panels every 30 seconds.
- The response includes `source`, `cache_status`, `refresh_seconds`, and `as_of`.
- Exchange/vendor delay may still apply. For direct tick-level data, connect a paid market data feed later.

Analysis pipeline:

- `collector-cronjob`: every 10 minutes, stores market data.
- `analyzer-cronjob`: every 15 minutes, computes market mood, risk score, and asset signals.
- `daily-report-cronjob`: 07:30 KST on weekdays, generates the Daily Report.
- `sms-morning-report-cronjob`: 07:35 KST on weekdays, sends the Daily Report by SMS.
- `sms-risk-alert-cronjob`: every 15 minutes, sends risk alert SMS through the configured provider.
- MVP storage uses the existing persistent app database. The repository layer is isolated so it can be migrated to PostgreSQL next.

Run the full MVP flow manually:

```bash
curl -X POST http://192.168.55.42:31081/api/analyze/run \
  -H 'Content-Type: application/json' \
  -d '{"provider":"mock"}'
```

Analysis APIs:

```text
POST /api/analyze/run
GET /api/analyze/latest
GET /api/market-score/latest
GET /api/signals/latest
GET /api/reports/daily/latest
POST /api/reports/daily/send-sms
```

SMS behavior:

- Default provider is `mock`; no real SMS is sent.
- Real sending happens only with `SMS_PROVIDER=solapi` or `SMS_PROVIDER=sens`.
- Phone numbers are normalized to `01012345678` format.
- Failures are stored in `notification_logs.error_message`.
- Solapi can send SMS/LMS/MMS through its API. Set `SOLAPI_API_KEY` and `SOLAPI_API_SECRET`.
- Naver Cloud SENS uses access key, secret key, and service id. Set `NAVER_SENS_ACCESS_KEY`, `NAVER_SENS_SECRET_KEY`, and `NAVER_SENS_SERVICE_ID`.
- Real providers may create external SMS charges.

SMS Secret values:

```text
SMS_PROVIDER=mock
SMS_SENDER_NUMBER=01000000000
SMS_RECIPIENT_NUMBER=01000000000
SOLAPI_API_KEY=replace-me
SOLAPI_API_SECRET=replace-me
NAVER_SENS_ACCESS_KEY=replace-me
NAVER_SENS_SECRET_KEY=replace-me
NAVER_SENS_SERVICE_ID=replace-me
```

Test SMS:

```bash
curl -X POST http://192.168.55.42:31081/api/notifications/sms/test \
  -H 'Content-Type: application/json' \
  -d '{"recipient":"01012345678"}'
```

Check delivery failures:

```bash
curl http://192.168.55.42:31081/api/notifications
```

Create or update a report subscription:

```bash
curl -X POST http://192.168.55.42:31081/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{"report_type":"morning","channel_type":"sms","recipient":"010-0000-0000","send_time":"07:30","timezone":"Asia/Seoul"}'
```

SMS and Kakao are mock providers now. They keep the same provider interface so Naver Cloud SENS, AWS SNS, Twilio, Solapi, BizMessage, Aligo, or Kakao official notification APIs can be added without changing the report pipeline.

## UI Principles

- Home first: understand today's market mood within five seconds.
- Card summary first, then drill down into reports and alerts.
- Plain language before jargon, with status badges for Risk On, Risk Off, Dollar Strong, Volatility Watch, and Rebalance Needed.
- Avoid "buy", "guaranteed return", or "sure opportunity"; use "reference signal" and "allocation reduction review".
