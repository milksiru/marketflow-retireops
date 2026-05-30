from app import db
from app.providers import ProviderError, provider_for
from app.reports import build_report


def send_notification(channel, recipient, report_type="morning", title=None, message=None):
    report = build_report(report_type)
    title = title or report["title"]
    message = message or report["message"]
    try:
        provider_for(channel).send_message(recipient, title, message)
        db.log_notification(channel, report_type, recipient, title, message, "sent")
        return {"status": "sent"}
    except ProviderError as exc:
        db.log_notification(channel, report_type, recipient, title, message, "failed", str(exc))
        return {"status": "failed", "error": str(exc)}
    except Exception as exc:
        db.log_notification(channel, report_type, recipient, title, message, "failed", str(exc))
        return {"status": "failed", "error": str(exc)}
