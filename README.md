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
