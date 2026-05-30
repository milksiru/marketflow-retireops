import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    KST = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    KST = timezone(timedelta(hours=9), "Asia/Seoul")


CACHE_TTL_SECONDS = 25
_CACHE = {"expires": 0, "data": None}

INDEX_SYMBOLS = [
    ("^GSPC", "S&P500", "US Large Cap", "US"),
    ("^IXIC", "Nasdaq", "US Tech", "US"),
    ("^KS11", "KOSPI", "Korea", "KR"),
    ("^N225", "Nikkei", "Japan", "JP"),
    ("KRW=X", "USD/KRW", "FX", "FX"),
    ("^TNX", "US10Y", "Treasury", "Bond"),
    ("^VIX", "VIX", "Volatility", "US"),
    ("BTC-USD", "BTC", "Crypto", "24H"),
]

TRADE_SYMBOLS = [
    ("NVDA", "NVIDIA"),
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("TSLA", "Tesla"),
    ("SOXX", "Semiconductor ETF"),
    ("QQQ", "Nasdaq 100 ETF"),
    ("TLT", "Long Bond ETF"),
    ("SCHD", "Dividend ETF"),
]


def _fmt_number(value, digits=2):
    if value is None:
        return "-"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".")


def _tone(change_percent):
    if change_percent is None:
        return "flat"
    if change_percent >= 0.25:
        return "up"
    if change_percent <= -0.25:
        return "down"
    return "flat"


def _change_text(change_percent):
    if change_percent is None:
        return "-"
    sign = "+" if change_percent >= 0 else ""
    return f"{sign}{change_percent:.2f}%"


def _spark(closes):
    values = [v for v in closes if isinstance(v, (int, float))]
    if len(values) < 2:
        return [50, 50, 50, 50, 50, 50, 50, 50]
    if len(values) > 8:
        step = max(1, len(values) // 8)
        values = values[-(step * 8) :: step][:8]
    if len(values) < 8:
        values = ([values[0]] * (8 - len(values))) + values
    return [round(v, 4) for v in values[-8:]]


def _signal(change_percent, symbol):
    if symbol in {"TLT", "^TNX"}:
        if change_percent and change_percent > 0.25:
            return "Rate Pressure"
        if change_percent and change_percent < -0.25:
            return "Relief"
        return "Rate Watch"
    if change_percent is None:
        return "Checking"
    if change_percent >= 2:
        return "Momentum"
    if change_percent >= 0.5:
        return "Trend"
    if change_percent <= -1:
        return "Volatile"
    return "Neutral"


def _volume_label(tone, symbol):
    if symbol == "BTC-USD":
        return "24H"
    if tone == "up":
        return "Active"
    if tone == "down":
        return "Risk"
    return "Watch"


def _fetch_chart(symbols):
    charts = {}
    for symbol in symbols:
        query = urllib.parse.quote(symbol, safe="")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{query}?range=1d&interval=5m"
        req = urllib.request.Request(url, headers={"User-Agent": "MarketFlow-RetireOps/1.0"})
        with urllib.request.urlopen(req, timeout=8) as res:
            payload = json.loads(res.read().decode())
        results = payload.get("chart", {}).get("result") or []
        if results:
            charts[symbol] = results[0]
    return charts


def _quote_from_chart(raw):
    meta = raw.get("meta", {})
    quote = (raw.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    price = meta.get("regularMarketPrice")
    previous = meta.get("previousClose")
    if price is None:
        numeric_closes = [v for v in closes if isinstance(v, (int, float))]
        price = numeric_closes[-1] if numeric_closes else None
    change_percent = None
    if price is not None and previous:
        change_percent = ((price - previous) / previous) * 100
    return {
        "price": price,
        "change_percent": change_percent,
        "spark": _spark(closes),
        "exchange_time": meta.get("regularMarketTime"),
    }


def _build_snapshot(charts):
    now = datetime.now(KST)
    indices = []
    for yahoo, symbol, name, session in INDEX_SYMBOLS:
        quote = _quote_from_chart(charts[yahoo])
        tone = "warn" if symbol in {"USD/KRW", "US10Y"} and quote["change_percent"] and quote["change_percent"] > 0 else _tone(quote["change_percent"])
        value = _fmt_number(quote["price"], 2)
        if symbol == "US10Y" and quote["price"] is not None:
            value = f"{quote['price']:.2f}%"
        indices.append(
            {
                "symbol": symbol,
                "name": name,
                "value": value,
                "change": _change_text(quote["change_percent"]),
                "tone": tone,
                "session": session,
                "volume": _volume_label(tone, yahoo),
                "spark": quote["spark"],
            }
        )

    trade_board = []
    for yahoo, name in TRADE_SYMBOLS:
        quote = _quote_from_chart(charts[yahoo])
        tone = _tone(quote["change_percent"])
        trade_board.append(
            {
                "symbol": yahoo,
                "name": name,
                "price": _fmt_number(quote["price"], 2),
                "change": _change_text(quote["change_percent"]),
                "tone": tone,
                "signal": _signal(quote["change_percent"], yahoo),
                "spark": quote["spark"],
            }
        )

    positive = sum(1 for item in trade_board if item["tone"] == "up")
    avg_change = sum(
        _quote_from_chart(charts[yahoo])["change_percent"] or 0 for yahoo, _ in TRADE_SYMBOLS
    ) / len(TRADE_SYMBOLS)
    mood_state = "Risk On" if positive >= 5 and avg_change >= 0 else "Neutral" if positive >= 3 else "Risk Off"
    mood_score = max(10, min(95, int(50 + avg_change * 8 + (positive - 4) * 5)))

    return {
        "as_of": now.isoformat(),
        "source": "yahoo-finance-chart",
        "refresh_seconds": CACHE_TTL_SECONDS,
        "mood": {
            "state": mood_state,
            "score": mood_score,
            "plain": "주요 글로벌 지수와 관심 종목의 최신 조회값을 기준으로 산출한 시장 상태입니다.",
            "drivers": [
                f"관심 종목 {positive}/{len(trade_board)}개 상승",
                f"관심 종목 평균 등락률 {_change_text(avg_change)}",
                "환율, 금리, 변동성은 별도 위험 신호로 계속 확인",
            ],
        },
        "badges": [mood_state, "Live Polling", "Exchange Delay Possible"],
        "indices": indices,
        "trade_board": trade_board,
    }


def live_market_snapshot():
    now = time.time()
    if _CACHE["data"] and _CACHE["expires"] > now:
        cached = dict(_CACHE["data"])
        cached["cache_status"] = "hit"
        return cached
    symbols = [item[0] for item in INDEX_SYMBOLS] + [item[0] for item in TRADE_SYMBOLS]
    try:
        charts = _fetch_chart(symbols)
        missing = [symbol for symbol in symbols if symbol not in charts]
        if missing:
            raise RuntimeError(f"missing market symbols: {', '.join(missing)}")
        snapshot = _build_snapshot(charts)
        snapshot["cache_status"] = "refresh"
        _CACHE["data"] = snapshot
        _CACHE["expires"] = now + CACHE_TTL_SECONDS
        return snapshot
    except Exception as exc:
        if _CACHE["data"]:
            cached = dict(_CACHE["data"])
            cached["cache_status"] = "stale"
            cached["source_error"] = str(exc)
            return cached
        return None
