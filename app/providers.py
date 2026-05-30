import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    channel = "base"

    def validate_config(self):
        return True

    def send_message(self, recipient, title, message):
        raise NotImplementedError

    def send_report(self, recipient, report):
        return self.send_message(recipient, report["title"], report["message"])


class EmailProvider(BaseProvider):
    channel = "email"

    def validate_config(self):
        required = ["EMAIL_SMTP_HOST", "EMAIL_SMTP_USER", "EMAIL_SMTP_PASSWORD"]
        missing = [key for key in required if not os.environ.get(key)]
        if missing:
            raise ProviderError(f"missing email config: {', '.join(missing)}")

    def send_message(self, recipient, title, message):
        self.validate_config()
        msg = EmailMessage()
        msg["From"] = os.environ["EMAIL_SMTP_USER"]
        msg["To"] = recipient
        msg["Subject"] = title
        msg.set_content(message)
        host = os.environ["EMAIL_SMTP_HOST"]
        port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(os.environ["EMAIL_SMTP_USER"], os.environ["EMAIL_SMTP_PASSWORD"])
            smtp.send_message(msg)


class TeamsProvider(BaseProvider):
    channel = "teams"

    def send_message(self, recipient, title, message):
        webhook = os.environ.get("TEAMS_WEBHOOK_URL") or recipient
        if not webhook:
            raise ProviderError("missing Teams webhook")
        payload = json.dumps({"title": title, "text": message}).encode()
        req = urllib.request.Request(
            webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()


class TelegramProvider(BaseProvider):
    channel = "telegram"

    def send_message(self, recipient, title, message):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID") or recipient
        if not token or not chat_id:
            raise ProviderError("missing Telegram token or chat id")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": f"{title}\n\n{message}"}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()


class MockSmsProvider(BaseProvider):
    channel = "sms"

    def send_message(self, recipient, title, message):
        print(f"[mock-sms] to={recipient} title={title} message={message}", flush=True)


class MockKakaoProvider(BaseProvider):
    channel = "kakao"

    def send_message(self, recipient, title, message):
        print(f"[mock-kakao] to={recipient} title={title} message={message}", flush=True)


PROVIDERS = {
    "email": EmailProvider(),
    "teams": TeamsProvider(),
    "telegram": TelegramProvider(),
    "sms": MockSmsProvider(),
    "kakao": MockKakaoProvider(),
}


def provider_for(channel):
    try:
        return PROVIDERS[channel]
    except KeyError as exc:
        raise ProviderError(f"unknown channel: {channel}") from exc
