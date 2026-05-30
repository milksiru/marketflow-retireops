import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
import urllib.request
from datetime import datetime, timezone

from app import db


class SmsError(RuntimeError):
    pass


def normalize_phone(value):
    return re.sub(r"\D", "", value or "")


def default_sender():
    return normalize_phone(os.environ.get("SMS_SENDER_NUMBER", "01000000000"))


def default_recipient():
    return normalize_phone(os.environ.get("SMS_RECIPIENT_NUMBER", "01000000000"))


class SmsProvider:
    name = "base"

    def send(self, sender, recipient, title, message):
        raise NotImplementedError


class MockSmsProvider(SmsProvider):
    name = "mock"

    def send(self, sender, recipient, title, message):
        print(f"[mock-sms] from={sender} to={recipient} title={title} message={message}", flush=True)
        return {"provider": self.name, "mock": True}


class SolapiSmsProvider(SmsProvider):
    name = "solapi"

    def send(self, sender, recipient, title, message):
        api_key = os.environ.get("SOLAPI_API_KEY")
        api_secret = os.environ.get("SOLAPI_API_SECRET")
        if not api_key or not api_secret:
            raise SmsError("missing Solapi credentials")
        date = datetime.now(timezone.utc).isoformat()
        salt = uuid.uuid4().hex
        signature = hmac.new(api_secret.encode(), f"{date}{salt}".encode(), hashlib.sha256).hexdigest()
        payload = {
            "message": {
                "to": recipient,
                "from": sender,
                "text": message,
            }
        }
        if title:
            payload["message"]["subject"] = title[:40]
        req = urllib.request.Request(
            "https://api.solapi.com/messages/v4/send",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode() or "{}")


class SensSmsProvider(SmsProvider):
    name = "sens"

    def send(self, sender, recipient, title, message):
        access_key = os.environ.get("NAVER_SENS_ACCESS_KEY")
        secret_key = os.environ.get("NAVER_SENS_SECRET_KEY")
        service_id = os.environ.get("NAVER_SENS_SERVICE_ID")
        if not access_key or not secret_key or not service_id:
            raise SmsError("missing Naver SENS credentials")
        timestamp = str(int(time.time() * 1000))
        uri = f"/sms/v2/services/{service_id}/messages"
        signature_body = f"POST {uri}\n{timestamp}\n{access_key}"
        signature = base64.b64encode(
            hmac.new(secret_key.encode(), signature_body.encode(), hashlib.sha256).digest()
        ).decode()
        payload = {
            "type": "LMS" if len(message.encode("utf-8")) > 90 or title else "SMS",
            "from": sender,
            "content": message,
            "messages": [{"to": recipient}],
        }
        if title:
            payload["subject"] = title[:40]
        req = urllib.request.Request(
            f"https://sens.apigw.ntruss.com{uri}",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "x-ncp-apigw-timestamp": timestamp,
                "x-ncp-iam-access-key": access_key,
                "x-ncp-apigw-signature-v2": signature,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode() or "{}")


def provider():
    selected = os.environ.get("SMS_PROVIDER", "mock").lower()
    if selected == "solapi":
        return SolapiSmsProvider()
    if selected == "sens":
        return SensSmsProvider()
    return MockSmsProvider()


def send_sms(title, message, recipient=None, report_type="manual", retries=1):
    sms_provider = provider()
    sender = default_sender()
    recipient = normalize_phone(recipient or default_recipient())
    last_error = None
    for attempt in range(retries + 1):
        try:
            result = sms_provider.send(sender, recipient, title, message)
            db.log_notification("sms", report_type, recipient, title, message, "sent")
            return {"status": "sent", "provider": sms_provider.name, "attempt": attempt + 1, "result": result}
        except Exception as exc:
            last_error = str(exc)
            if attempt >= retries:
                db.log_notification("sms", report_type, recipient, title, message, "failed", last_error)
                return {"status": "failed", "provider": sms_provider.name, "error": last_error}
    return {"status": "failed", "provider": sms_provider.name, "error": last_error}


def morning_template(report):
    return (
        "[MarketFlow]\n"
        f"오늘 시장: {report.get('market_mood', '-')}\n"
        f"위험도: {report.get('risk_level', '-')}\n\n"
        f"요약:\n{report.get('summary', '-')}\n\n"
        f"DC 참고:\n{report.get('dc_comment', '-')}"
    )


def risk_template(signal):
    return (
        "[MarketFlow 위험알림]\n"
        f"{signal.get('signal_type', 'Risk Alert')}\n\n"
        f"상태: {signal.get('severity', '-')}\n"
        f"원인: {signal.get('reason', '-')}\n\n"
        f"확인:\n{os.environ.get('DASHBOARD_URL', 'http://192.168.55.42:31081')}"
    )
