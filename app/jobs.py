import argparse
import os

from app.notifications import send_notification
from app.pipeline import (
    collect_market_data,
    generate_daily_report,
    run_analysis,
    send_daily_report_sms,
    send_risk_alert_sms,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_type")
    parser.add_argument("--channel", default=os.environ.get("REPORT_CHANNEL", "sms"))
    parser.add_argument("--recipient", default=os.environ.get("REPORT_RECIPIENT", "scheduled-recipient"))
    parser.add_argument("--provider", default=os.environ.get("MARKETFLOW_COLLECTOR_PROVIDER", "mock"))
    args = parser.parse_args()
    if args.report_type == "collect":
        print(collect_market_data(args.provider), flush=True)
        return
    if args.report_type == "analyze":
        print(run_analysis(), flush=True)
        return
    if args.report_type == "daily-report":
        print(generate_daily_report(), flush=True)
        return
    if args.report_type == "send-sms-report":
        print(send_daily_report_sms(), flush=True)
        return
    if args.report_type == "send-risk-alert":
        print(send_risk_alert_sms(), flush=True)
        return
    result = send_notification(args.channel, args.recipient, args.report_type)
    print(result, flush=True)


if __name__ == "__main__":
    main()
