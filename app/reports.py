from datetime import datetime
from zoneinfo import ZoneInfo


REPORTS = {
    "morning": {
        "title": "Morning Brief",
        "bullets": [
            "US market close was constructive with technology leadership.",
            "Watch USD/KRW and US 10Y before adding risk.",
            "DC 참고: 신규 납입금은 과열 섹터보다 분산 비중을 우선 점검하세요.",
        ],
    },
    "market-open": {
        "title": "Market Open Watch",
        "bullets": [
            "Pre-open mood is Neutral to Risk On.",
            "Semiconductor strength is supportive, but volatility remains elevated.",
            "Check FX and futures before market open.",
        ],
    },
    "evening": {
        "title": "Evening Brief",
        "bullets": [
            "Korea market close requires sector confirmation.",
            "Watchlist ETF moves are summarized for next-session planning.",
            "Risk alert: avoid interpreting short-term strength as guaranteed return.",
        ],
    },
    "weekly": {
        "title": "Weekly Report",
        "bullets": [
            "Review weekly winners and weak sectors.",
            "Prepare next-week watch points.",
            "DC 리밸런싱 참고: 목표 비중 이탈 여부를 점검하세요.",
        ],
    },
    "monthly-dc": {
        "title": "Monthly DC Report",
        "bullets": [
            "Review monthly asset flow and target allocation drift.",
            "Plan new contribution allocation.",
            "Risk score changed: confirm before increasing equity exposure.",
        ],
    },
}


def market_snapshot():
    return {
        "mood": "Risk On",
        "badges": ["Risk On", "Dollar Strong", "Volatility Watch"],
        "indices": [
            {"symbol": "S&P500", "value": "+1.2%"},
            {"symbol": "Nasdaq", "value": "+1.6%"},
            {"symbol": "KOSPI", "value": "+0.4%"},
            {"symbol": "USD/KRW", "value": "1,360"},
            {"symbol": "US10Y", "value": "4.32%"},
            {"symbol": "VIX", "value": "15.8"},
        ],
        "watchlist": [
            {"symbol": "SOXX", "signal": "Strong, but overheated"},
            {"symbol": "QQQ", "signal": "Trend positive"},
            {"symbol": "TLT", "signal": "Rate-sensitive watch"},
        ],
        "dc": {
            "style": "Balanced accumulation",
            "rebalance": "Check equity overweight before new contributions",
            "plain_language": "금리가 빠르게 오르면 성장주에는 부담이 될 수 있습니다.",
        },
    }


def build_report(report_type):
    report = REPORTS.get(report_type, REPORTS["morning"]).copy()
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    report["report_type"] = report_type
    report["generated_at"] = now.isoformat()
    report["snapshot"] = market_snapshot()
    report["message"] = "\n".join(f"- {item}" for item in report["bullets"])
    return report
