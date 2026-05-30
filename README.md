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
- Notification API:
  - `GET /api/notifications`
  - `GET /api/notifications/channels`
  - `POST /api/notifications/test`
  - `POST /api/notifications/send`
  - `PUT /api/notifications/channels/{channel}/settings`
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
