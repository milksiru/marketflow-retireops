from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import db
from app.marketdata import live_market_snapshot
from app.sms import morning_template, risk_template, send_sms


try:
    KST = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    KST = timezone(timedelta(hours=9), "Asia/Seoul")


TARGET_ASSETS = [
    "S&P500", "Nasdaq", "DOW", "KOSPI", "KOSDAQ", "USD/KRW", "US10Y", "VIX", "WTI", "GOLD", "BTC",
    "QQQ", "SPY", "VOO", "SOXX", "SMH", "SCHD", "TLT", "NVDA", "MSFT", "AAPL", "삼성전자", "SK하이닉스",
]


MOCK_PRICES = {
    "S&P500": (5304, 0.8), "Nasdaq": (16920, 1.1), "DOW": (39120, 0.2), "KOSPI": (2724, 0.4),
    "KOSDAQ": (847, -0.2), "USD/KRW": (1360, 0.3), "US10Y": (4.32, 0.9), "VIX": (15.8, -2.2),
    "WTI": (79.2, 1.4), "GOLD": (2340, 0.5), "BTC": (68420, 2.4), "QQQ": (458.5, 1.5),
    "SPY": (528.2, 0.9), "VOO": (486.1, 0.9), "SOXX": (240.8, 2.1), "SMH": (252.4, 2.3),
    "SCHD": (78.6, 0.2), "TLT": (91.4, -0.8), "NVDA": (211.14, -1.45), "MSFT": (431.6, 1.1),
    "AAPL": (191.2, 0.9), "삼성전자": (78200, 0.7), "SK하이닉스": (196000, 1.8),
}


def _now():
    return datetime.now(KST)


def _risk_level(score):
    if score <= 20:
        return "LOW"
    if score <= 40:
        return "NORMAL"
    if score <= 60:
        return "WATCH"
    if score <= 80:
        return "WARNING"
    return "HIGH RISK"


def collect_market_data(provider="mock"):
    run_id = db.create_analysis_run("collector")
    try:
        observed_at = _now().isoformat()
        rows = []
        if provider == "live":
            snapshot = live_market_snapshot()
            for item in snapshot.get("indices", []):
                rows.append(_row(item["symbol"], item["name"], item["value"], item["change"], snapshot["source"], observed_at))
            for item in snapshot.get("trade_board", []):
                rows.append(_row(item["symbol"], item["name"], item["price"], item["change"], snapshot["source"], observed_at))
        else:
            rows = [
                {
                    "asset_id": asset,
                    "asset_name": asset,
                    "price": price,
                    "change_percent": change,
                    "volume": 1000000,
                    "source": "mock",
                    "observed_at": observed_at,
                }
                for asset, (price, change) in MOCK_PRICES.items()
            ]
        count = db.insert_market_prices(rows)
        db.finish_analysis_run(run_id)
        return {"status": "collected", "provider": provider, "count": count}
    except Exception as exc:
        db.finish_analysis_run(run_id, "failed", str(exc))
        raise


def _row(asset_id, name, price_text, change_text, source, observed_at):
    price = float(str(price_text).replace(",", "").replace("%", "")) if price_text not in {"-", None} else None
    change = float(str(change_text).replace("%", "")) if change_text not in {"-", None} else 0
    return {
        "asset_id": asset_id,
        "asset_name": name,
        "price": price,
        "change_percent": change,
        "volume": 1000000,
        "source": source,
        "observed_at": observed_at,
    }


def run_analysis():
    run_id = db.create_analysis_run("analyzer")
    try:
        prices = db.latest_market_prices()
        if not prices:
            collect_market_data("mock")
            prices = db.latest_market_prices()
        by_id = {row["asset_id"]: row for row in prices}
        nasdaq = by_id.get("Nasdaq", {}).get("change_percent") or 0
        vix = by_id.get("VIX", {}).get("price") or 0
        vix_change = by_id.get("VIX", {}).get("change_percent") or 0
        us10y_change = by_id.get("US10Y", {}).get("change_percent") or 0
        usdkrw_change = by_id.get("USD/KRW", {}).get("change_percent") or 0
        soxx_change = by_id.get("SOXX", {}).get("change_percent") or 0
        wti_change = by_id.get("WTI", {}).get("change_percent") or 0

        mood = "Neutral"
        if vix >= 25:
            mood = "Volatility Alert"
        elif nasdaq > 0 and vix_change < 0:
            mood = "Risk On"
        elif nasdaq < 0 and vix_change > 0:
            mood = "Risk Off"
        if us10y_change >= 1:
            mood = "Rate Pressure"
        if usdkrw_change >= 0.8:
            mood = "Dollar Strong"

        risk = 20
        risk += 25 if vix >= 25 else 10 if vix >= 18 else 0
        risk += 15 if us10y_change >= 1 else 0
        risk += 15 if usdkrw_change >= 0.8 else 0
        risk += 15 if nasdaq <= -1 else 0
        risk += 10 if soxx_change <= -1 else 0
        risk += 10 if wti_change >= 3 else 0
        risk = max(0, min(100, risk))

        score = {
            "score_date": _now().date().isoformat(),
            "market_mood": mood,
            "risk_score": risk,
            "risk_level": _risk_level(risk),
            "summary": f"{mood}: NASDAQ {nasdaq:+.2f}%, VIX {vix:.2f}, USD/KRW {usdkrw_change:+.2f}%, US10Y {us10y_change:+.2f}%",
        }
        db.insert_market_score(score)
        signals = build_signals(prices, risk)
        db.insert_asset_signals(signals)
        db.finish_analysis_run(run_id)
        return {"status": "analyzed", "market_score": score, "signals": signals}
    except Exception as exc:
        db.finish_analysis_run(run_id, "failed", str(exc))
        raise


def build_signals(prices, risk_score):
    signals = []
    for row in prices:
        asset = row["asset_id"]
        change = row.get("change_percent") or 0
        score = 50 + int(change * 8)
        signal_type = "추세 확인"
        severity = "info"
        reason = f"최근 등락률 {change:+.2f}% 기준 참고 신호입니다."
        if change >= 2:
            signal_type = "모멘텀 양호"
            severity = "positive"
            reason = "1개월 수익률 강세와 거래량 증가 조건의 MVP 대체 신호입니다."
        if change <= -1.5:
            signal_type = "위험 신호"
            severity = "warning"
            reason = "MA120 이탈을 직접 계산하기 전까지 급락률을 위험 대체 신호로 사용합니다."
        if risk_score >= 61 and severity == "positive":
            signal_type = "공격 신호 낮춤"
            severity = "watch"
            reason = "VIX/금리/환율 위험 구간에서는 공격형 시그널을 낮춥니다."
        signals.append(
            {
                "asset_id": asset,
                "signal_type": signal_type,
                "score": max(0, min(100, score)),
                "severity": severity,
                "reason": reason,
            }
        )
    return signals


def generate_daily_report():
    run_id = db.create_analysis_run("daily-report")
    try:
        latest = db.latest_market_score()
        if not latest:
            run_analysis()
            latest = db.latest_market_score()
        signals = db.latest_asset_signals(12)
        strong = [s["asset_id"] for s in signals if s["severity"] in {"positive", "watch"}][:4]
        weak = [s["asset_id"] for s in signals if s["severity"] == "warning"][:4]
        dc_comment = (
            "자동 매수/매도는 제공하지 않습니다. 위험 구간에서는 채권/현금성 비중과 신규 납입금 배분을 점검하세요."
            if latest["risk_score"] >= 61
            else "신규 납입금은 목표 비중에서 부족한 자산을 보정하는 참고 기준으로 활용하세요."
        )
        content = "\n".join(
            [
                "1. 오늘 시장 상태",
                latest["summary"],
                "",
                "2. 강세 후보",
                ", ".join(strong) or "-",
                "",
                "3. 약세/위험 후보",
                ", ".join(weak) or "-",
                "",
                "4. DC 퇴직연금 운용 참고",
                dc_comment,
                "",
                "5. 오늘 점검할 항목",
                "VIX, US10Y, USD/KRW, NASDAQ, SOXX 흐름을 확인하세요.",
            ]
        )
        report = {
            "report_date": _now().date().isoformat(),
            "title": "MarketFlow Daily Report",
            "market_mood": latest["market_mood"],
            "risk_level": latest["risk_level"],
            "summary": latest["summary"],
            "dc_comment": dc_comment,
            "content": content,
        }
        db.insert_daily_report(report)
        db.finish_analysis_run(run_id)
        return {"status": "generated", "report": report}
    except Exception as exc:
        db.finish_analysis_run(run_id, "failed", str(exc))
        raise


def latest_analysis():
    return {
        "market_score": db.latest_market_score(),
        "signals": db.latest_asset_signals(25),
        "daily_report": db.latest_daily_report(),
    }


def send_daily_report_sms():
    report = db.latest_daily_report()
    if not report:
        report = generate_daily_report()["report"]
    return send_sms("MarketFlow Daily", morning_template(report), report_type="daily-report", retries=1)


def send_risk_alert_sms():
    signals = db.latest_asset_signals(10)
    signal = next((item for item in signals if item["severity"] == "warning"), signals[0] if signals else None)
    if not signal:
        run_analysis()
        signals = db.latest_asset_signals(10)
        signal = signals[0]
    return send_sms("MarketFlow Risk", risk_template(signal), report_type="risk-alert", retries=1)
