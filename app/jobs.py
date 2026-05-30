import argparse
import os

from app.notifications import send_notification


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_type")
    parser.add_argument("--channel", default=os.environ.get("REPORT_CHANNEL", "sms"))
    parser.add_argument("--recipient", default=os.environ.get("REPORT_RECIPIENT", "scheduled-recipient"))
    args = parser.parse_args()
    result = send_notification(args.channel, args.recipient, args.report_type)
    print(result, flush=True)


if __name__ == "__main__":
    main()
