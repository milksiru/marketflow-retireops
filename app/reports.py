from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import db
from app.marketdata import live_market_snapshot


try:
    KST = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    KST = timezone(timedelta(hours=9), "Asia/Seoul")


REPORTS = {
    "morning": {
        "title": "Morning Brief",
        "label": "오전 브리프",
        "send_time": "07:30",
        "summary": "미국장 마감과 오늘 한국장 체크포인트를 5줄로 정리합니다.",
        "bullets": [
            "미국 기술주는 강세였고 반도체가 흐름을 이끌었습니다.",
            "달러/원과 미국 10년 금리가 장 초반 방향을 정할 가능성이 큽니다.",
            "VIX는 낮지만 이벤트 전에는 변동성 확대를 염두에 두세요.",
            "관심 ETF는 SOXX, QQQ, TLT 순서로 신호를 확인하세요.",
            "DC 참고: 신규 납입금은 과열 섹터보다 배당/채권 비중 보정 후보를 먼저 점검하세요.",
        ],
    },
    "market-open": {
        "title": "Market Open Watch",
        "label": "개장 전 체크",
        "send_time": "08:50",
        "summary": "환율, 선물, 전일 미국 지수, 반도체 흐름을 개장 전에 확인합니다.",
        "bullets": [
            "개장 전 분위기는 Neutral에서 Risk On 사이입니다.",
            "미국 선물과 원화 흐름이 동시에 안정되면 성장주에 우호적입니다.",
            "반도체는 강하지만 단기 과열 구간에서는 분할 접근이 낫습니다.",
            "시장 초반 30분은 추격보다 확인이 우선입니다.",
            "DC 참고: 오늘 신호는 비중 확대보다 리밸런싱 확인에 가깝습니다.",
        ],
    },
    "evening": {
        "title": "Evening Brief",
        "label": "마감 브리프",
        "send_time": "18:30",
        "summary": "한국장 마감, 관심 종목/ETF 변화, 위험 알림을 정리합니다.",
        "bullets": [
            "한국장은 대형 기술주 중심으로 견조했지만 업종 확산은 제한적이었습니다.",
            "관심 ETF 중 SOXX는 강세 유지, TLT는 금리 민감 구간입니다.",
            "짧은 반등을 수익 보장으로 해석하지 마세요.",
            "내일은 환율과 외국인 수급을 먼저 확인하세요.",
            "DC 참고: 목표 비중 이탈 여부를 확인하고 신규 납입금 배분을 조정하세요.",
        ],
    },
    "weekly": {
        "title": "Weekly Report",
        "label": "주간 리포트",
        "send_time": "토요일 09:00",
        "summary": "주간 수익률, 강세/약세 섹터, 다음 주 관찰 포인트를 제공합니다.",
        "bullets": [
            "이번 주 강세 섹터는 반도체와 소프트웨어입니다.",
            "약세 섹터는 금리 민감도가 높은 채권형 자산입니다.",
            "다음 주에는 FOMC 발언, 고용 지표, 달러 흐름을 확인하세요.",
            "관심 종목은 확신보다 관찰 후보로 분리해 관리하세요.",
            "DC 참고: 목표 비중 대비 주식 비중이 높다면 신규 납입금은 안정 자산 보정 후보입니다.",
        ],
    },
    "monthly-dc": {
        "title": "Monthly DC Report",
        "label": "월간 DC 리포트",
        "send_time": "매월 1일 09:00",
        "summary": "월간 자산 흐름, 목표 비중 이탈, 신규 납입금 배분 참고를 정리합니다.",
        "bullets": [
            "월간 자산 흐름은 성장 자산 우위, 방어 자산 보합입니다.",
            "목표 비중에서 주식형 자산이 4.2%p 높아졌습니다.",
            "신규 납입금은 채권/배당형 보정 배분을 우선 검토하세요.",
            "위험 점수는 전월보다 소폭 상승했습니다.",
            "이 리포트는 투자 조언이 아니라 운용 참고 신호입니다.",
        ],
    },
}


def _now():
    return datetime.now(KST)


def market_snapshot():
    live = live_market_snapshot()
    if live:
        fallback = _fallback_market_snapshot()
        live["brief"] = fallback["brief"]
        live["watchlist"] = _watchlist_from_trade_board(live["trade_board"])
        live["sectors"] = _sectors_from_trade_board(live["trade_board"])
        live["dc"] = fallback["dc"]
        live["alerts"] = _alerts_from_live(live)
        live["rankings"] = _rankings_from_trade_board(live["trade_board"])
        live["news_sources"] = _market_news_sources()
        live["family_plan"] = _family_plan()
        live["taeri_plan"] = _taeri_plan()
        return live
    return _fallback_market_snapshot()


def _fallback_market_snapshot():
    return {
        "as_of": _now().isoformat(),
        "source": "fallback-sample",
        "refresh_seconds": 25,
        "mood": {
            "state": "Risk On",
            "score": 74,
            "plain": "위험자산 선호가 우세하지만 환율과 금리는 계속 확인해야 합니다.",
            "drivers": ["미국 기술주 강세", "반도체 수급 개선", "달러 강세 부담"],
        },
        "badges": ["Risk On", "Dollar Strong", "Volatility Watch"],
        "indices": [
            {"symbol": "S&P500", "name": "US Large Cap", "value": "5,304", "change": "+1.2%", "tone": "up", "session": "US", "volume": "High", "spark": [48, 50, 49, 53, 57, 56, 61, 64]},
            {"symbol": "Nasdaq", "name": "US Tech", "value": "16,920", "change": "+1.6%", "tone": "up", "session": "US", "volume": "High", "spark": [44, 47, 49, 52, 55, 59, 63, 67]},
            {"symbol": "KOSPI", "name": "Korea", "value": "2,724", "change": "+0.4%", "tone": "up", "session": "KR", "volume": "Normal", "spark": [51, 50, 52, 53, 52, 54, 55, 56]},
            {"symbol": "Nikkei", "name": "Japan", "value": "39,102", "change": "+0.7%", "tone": "up", "session": "JP", "volume": "Normal", "spark": [46, 48, 47, 50, 53, 52, 55, 58]},
            {"symbol": "USD/KRW", "name": "FX", "value": "1,360", "change": "+0.3%", "tone": "warn", "session": "FX", "volume": "Watch", "spark": [54, 55, 57, 56, 59, 60, 58, 61]},
            {"symbol": "US10Y", "name": "Treasury", "value": "4.32%", "change": "+4bp", "tone": "warn", "session": "Bond", "volume": "Watch", "spark": [49, 52, 53, 55, 54, 57, 59, 60]},
            {"symbol": "VIX", "name": "Volatility", "value": "15.8", "change": "-0.7", "tone": "down", "session": "US", "volume": "Low", "spark": [65, 63, 61, 58, 56, 55, 52, 50]},
            {"symbol": "BTC", "name": "Crypto", "value": "68,420", "change": "+2.4%", "tone": "up", "session": "24H", "volume": "Active", "spark": [42, 45, 44, 49, 52, 56, 58, 64]},
        ],
        "trade_board": [
            {"symbol": "NVDA", "name": "NVIDIA", "price": "1,128.4", "change": "+3.8%", "tone": "up", "signal": "Momentum", "spark": [38, 42, 45, 49, 55, 62, 66, 74]},
            {"symbol": "AAPL", "name": "Apple", "price": "191.2", "change": "+0.9%", "tone": "up", "signal": "Recovering", "spark": [48, 47, 49, 50, 52, 54, 53, 56]},
            {"symbol": "MSFT", "name": "Microsoft", "price": "431.6", "change": "+1.1%", "tone": "up", "signal": "Trend", "spark": [45, 47, 50, 51, 55, 57, 56, 60]},
            {"symbol": "TSLA", "name": "Tesla", "price": "178.0", "change": "-1.4%", "tone": "down", "signal": "Volatile", "spark": [61, 58, 60, 55, 52, 49, 47, 45]},
            {"symbol": "SOXX", "name": "Semiconductor ETF", "price": "240.8", "change": "+2.1%", "tone": "up", "signal": "Overheat", "spark": [44, 49, 54, 58, 63, 66, 68, 70]},
            {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "price": "458.5", "change": "+1.5%", "tone": "up", "signal": "Risk On", "spark": [43, 46, 48, 51, 55, 57, 60, 63]},
            {"symbol": "TLT", "name": "Long Bond ETF", "price": "91.4", "change": "-0.8%", "tone": "down", "signal": "Rate Pressure", "spark": [60, 58, 55, 54, 50, 48, 46, 45]},
            {"symbol": "SCHD", "name": "Dividend ETF", "price": "78.6", "change": "+0.2%", "tone": "flat", "signal": "Defensive", "spark": [50, 50, 51, 50, 52, 51, 52, 53]},
        ],
        "brief": [
            "오늘 시장은 기술주 중심의 Risk On 흐름입니다.",
            "달러 강세와 금리 상승은 추격 매수보다 확인을 요구합니다.",
            "반도체는 강하지만 단기 과열 신호를 함께 봐야 합니다.",
            "채권형 자산은 금리 민감도가 높아 분할 접근이 유리합니다.",
            "DC 운용은 신규 납입금으로 목표 비중을 보정하는 쪽이 자연스럽습니다.",
        ],
        "watchlist": [
            {"symbol": "SOXX", "name": "반도체 ETF", "signal": "강세 유지", "risk": "단기 과열", "score": 82, "change": "+2.1%"},
            {"symbol": "QQQ", "name": "나스닥 100", "signal": "상승 추세", "risk": "금리 민감", "score": 76, "change": "+1.5%"},
            {"symbol": "TLT", "name": "장기채 ETF", "signal": "관찰", "risk": "금리 상승", "score": 48, "change": "-0.8%"},
            {"symbol": "SCHD", "name": "배당 ETF", "signal": "방어 후보", "risk": "상승 탄력 제한", "score": 63, "change": "+0.2%"},
        ],
        "sectors": [
            {"name": "Semiconductor", "change": "+2.1%", "tone": "up"},
            {"name": "Software", "change": "+1.4%", "tone": "up"},
            {"name": "Bank", "change": "+0.3%", "tone": "flat"},
            {"name": "Battery", "change": "-0.6%", "tone": "down"},
            {"name": "Bond", "change": "-0.8%", "tone": "down"},
        ],
        "dc": {
            "style": "균형 적립형",
            "risk_score": 62,
            "rebalance": "주식형 비중이 목표보다 높아 신규 납입금은 배당/채권형 보정 후보입니다.",
            "allocation": [
                {"label": "주식형", "target": 55, "current": 59},
                {"label": "채권형", "target": 30, "current": 27},
                {"label": "배당/현금성", "target": 15, "current": 14},
            ],
            "plain_language": "금리가 빠르게 오르면 성장주에는 부담이 될 수 있습니다. 새 납입금은 과열 구간을 따라가기보다 부족한 비중을 채우는 방식이 안정적입니다.",
        },
        "alerts": [
            {"level": "watch", "title": "Dollar Strong", "message": "달러/원 상승은 외국인 수급에 부담이 될 수 있습니다."},
            {"level": "info", "title": "Rebalance Needed", "message": "주식형 비중이 목표보다 4%p 높습니다."},
            {"level": "watch", "title": "Volatility Watch", "message": "중요 지표 발표 전 변동성 확대 가능성이 있습니다."},
        ],
        "rankings": [
            {"rank": 1, "symbol": "NVDA", "name": "NVIDIA", "price": "1,128.4", "change": "+3.8%", "tone": "up", "signal": "Momentum"},
            {"rank": 2, "symbol": "SOXX", "name": "Semiconductor ETF", "price": "240.8", "change": "+2.1%", "tone": "up", "signal": "Overheat"},
            {"rank": 3, "symbol": "QQQ", "name": "Nasdaq 100 ETF", "price": "458.5", "change": "+1.5%", "tone": "up", "signal": "Risk On"},
            {"rank": 4, "symbol": "TLT", "name": "Long Bond ETF", "price": "91.4", "change": "-0.8%", "tone": "down", "signal": "Rate Pressure"},
        ],
        "news_sources": _market_news_sources(),
        "family_plan": _family_plan(),
        "taeri_plan": _taeri_plan(),
    }


def _money_krw(value):
    if value >= 100_000_000:
        eok = value // 100_000_000
        man = (value % 100_000_000) // 10_000
        return f"{eok}억 {man:,}만" if man else f"{eok}억"
    return f"{value // 10_000:,}만"


def _family_plan():
    defaults = {
        "cash_stock": 25_000_000,
        "park_juyoung_retirement": 15_000_000,
        "kim_jihun_retirement": 25_000_000,
        "savings": 600_000,
        "car_loan": 100_000_000,
        "jeonse_deposit": 250_000_000,
        "jeonse_loan": 109_000_000,
        "monthly_saving": 100_000,
        "home_target_low": 600_000_000,
        "home_target_high": 700_000_000,
    }


def _month_age(birth_date):
    today = _now().date()
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    if today.day < birth_date.day:
        months -= 1
    return months


def _taeri_plan():
    birth = datetime(2022, 11, 11, tzinfo=KST).date()
    months = _month_age(birth)
    years = months // 12
    remain_months = months % 12
    return {
        "name": "태리",
        "birth": "2022-11-11",
        "age": f"{years}세 {remain_months}개월",
        "profile": "여아 · 대한민국 · 어린이집 3년차",
        "summary": "올해는 어린이집 생활 안정, 언어 표현, 친구관계, 기본 생활습관, 4세 무상교육·보육 확대 여부 확인이 핵심입니다.",
        "checkpoints": [
            {"title": "어린이집 생활", "body": "등원 거부, 낮잠, 식사, 또래관계, 선생님 피드백을 월 1회 메모해 변화만 봅니다."},
            {"title": "언어·정서", "body": "문장으로 요구하기, 감정 이름 붙이기, 기다리기·양보하기를 놀이 속에서 반복합니다."},
            {"title": "건강", "body": "예방접종도우미에서 접종 누락 여부를 확인하고, 계절성 독감 접종 시기도 챙깁니다."},
            {"title": "기관 전환", "body": "어린이집 유지, 유치원 전환, 방과후 비용 차이를 2027년 전환 전에 비교합니다."},
        ],
        "todo": [
            "어린이집 상담 때 친구관계·식사·낮잠·화장실 적응을 확인합니다.",
            "예방접종도우미에서 태리 접종 내역과 다음 접종 일정을 확인합니다.",
            "4~5세 무상교육·보육 지원이 어린이집 필요경비에서 어떻게 차감되는지 기관에 확인합니다.",
            "긴급 돌봄 대비용으로 아이돌봄서비스 가입 가능 여부와 본인부담금을 미리 확인합니다.",
        ],
        "sources": [
            {
                "source": "정책브리핑 / 교육부",
                "title": "2026년부터 유아 무상교육·보육 지원 대상 4~5세 확대",
                "summary": "2026년 3월부터 4~5세 어린이집·유치원 이용 아동에 대한 추가 비용 지원 확대 내용을 확인했습니다.",
                "url": "https://m.korea.kr/briefing/pressReleaseView.do?newsId=156746963",
            },
            {
                "source": "찾기쉬운 생활법령정보",
                "title": "양육수당·보육 지원 기준",
                "summary": "어린이집, 유치원, 종일제 아이돌봄 이용 여부에 따른 양육수당 지원 조건을 확인했습니다.",
                "url": "https://www.easylaw.go.kr/CSP/CnpClsMain.laf?ccfNo=3&cciNo=1&cnpClsNo=1&csmSeq=626",
            },
            {
                "source": "질병관리청 예방접종도우미",
                "title": "어린이 국가예방접종 확인",
                "summary": "어린이 예방접종 기록과 지정의료기관 확인을 위한 공식 서비스입니다.",
                "url": "https://nip.kdca.go.kr/",
            },
            {
                "source": "아이돌봄서비스",
                "title": "만 12세 이하 아이돌봄 지원",
                "summary": "양육공백이 생길 때 아이돌보미가 방문하는 정부지원 돌봄 서비스를 확인했습니다.",
                "url": "https://www.idolbom.go.kr/front/srvcGuide",
            },
        ],
    }
    settings = {**defaults, **db.family_plan_settings()}
    cash_stock = settings["cash_stock"]
    wife_cash = settings["park_juyoung_retirement"]
    severance = settings["kim_jihun_retirement"]
    savings = settings["savings"]
    car_loan = settings["car_loan"]
    jeonse_deposit = settings["jeonse_deposit"]
    jeonse_loan = settings["jeonse_loan"]
    liquid_assets = cash_stock + wife_cash + severance + savings
    housing_equity = jeonse_deposit - jeonse_loan
    current_net = liquid_assets + housing_equity - car_loan
    home_target_low = settings["home_target_low"]
    home_target_high = settings["home_target_high"]
    target_mid = (home_target_low + home_target_high) // 2
    recommended_base_cash = 220_000_000
    available_home_base = liquid_assets + housing_equity
    gap = max(0, recommended_base_cash - available_home_base)
    monthly_saving = settings["monthly_saving"]
    return {
        "title": "우리 가족 플랜",
        "target": "집 매매 6억~7억",
        "summary": "전세 순자산과 현금성 자산을 합치면 매매 진입선에는 근접했지만, 차 할부 1억 때문에 안전마진 관리가 먼저입니다.",
        "assets": [
            {"label": "현금/주식", "value": _money_krw(cash_stock)},
            {"label": "박주영님 퇴직금", "value": _money_krw(wife_cash)},
            {"label": "김지훈님 퇴직금", "value": _money_krw(severance)},
            {"label": "예적금", "value": _money_krw(savings)},
            {"label": "전세 순자산", "value": _money_krw(housing_equity)},
        ],
        "debts": [
            {"label": "차 할부", "value": _money_krw(car_loan)},
            {"label": "전세 대출", "value": _money_krw(jeonse_loan)},
        ],
        "metrics": [
            {"label": "가용 자금", "value": _money_krw(available_home_base)},
            {"label": "순자산 추정", "value": _money_krw(current_net)},
            {"label": "목표 기준", "value": _money_krw(target_mid)},
        ],
        "goals": [
            {"label": "매매 준비금", "current": available_home_base, "target": recommended_base_cash, "caption": f"부대비용 포함 기준, 부족분 {_money_krw(gap)}"},
            {"label": "비상금", "current": savings, "target": 10_000_000, "caption": "생활 안정성 우선"},
            {"label": "차 할부 관리", "current": max(0, car_loan - 30_000_000), "target": car_loan, "caption": "최소 3천만 선상환 후보"},
        ],
        "steps": [
            "1단계: 예적금/비상금 1,000만 원을 먼저 확보합니다.",
            "2단계: 차 할부는 금리와 중도상환수수료를 보고 3,000만 원 이상 감축 후보로 봅니다.",
            "3단계: 6억~7억 매매는 전세 순자산 반환 시점을 기준으로 대출 한도와 월 상환액을 같이 계산합니다.",
            "4단계: 투자 자산은 매수보다 주택 계약금·취득세·이사비 현금흐름을 우선합니다.",
        ],
        "monthly_saving": _money_krw(monthly_saving),
        "editable": [
            {"key": "cash_stock", "label": "현금/주식", "value": cash_stock, "category": "asset"},
            {"key": "park_juyoung_retirement", "label": "박주영님 퇴직금", "value": wife_cash, "category": "asset"},
            {"key": "kim_jihun_retirement", "label": "김지훈님 퇴직금", "value": severance, "category": "asset"},
            {"key": "savings", "label": "예적금", "value": savings, "category": "asset"},
            {"key": "jeonse_deposit", "label": "전세 보증금", "value": jeonse_deposit, "category": "asset"},
            {"key": "car_loan", "label": "차 할부", "value": car_loan, "category": "debt"},
            {"key": "jeonse_loan", "label": "전세 대출", "value": jeonse_loan, "category": "debt"},
            {"key": "monthly_saving", "label": "월 예적금", "value": monthly_saving, "category": "plan"},
            {"key": "home_target_low", "label": "목표 매매가 하단", "value": home_target_low, "category": "plan"},
            {"key": "home_target_high", "label": "목표 매매가 상단", "value": home_target_high, "category": "plan"},
        ],
    }


def _watchlist_from_trade_board(trade_board):
    risks = {
        "SOXX": "단기 과열",
        "QQQ": "금리 민감",
        "TLT": "금리 상승",
        "SCHD": "상승 탄력 제한",
    }
    items = []
    for item in trade_board:
        if item["symbol"] not in risks:
            continue
        change = item["change"]
        numeric = float(change.replace("%", "")) if change not in {"-", ""} else 0
        score = max(15, min(95, int(55 + numeric * 8)))
        items.append(
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "signal": item["signal"],
                "risk": risks[item["symbol"]],
                "score": score,
                "change": change,
            }
        )
    return items


def _sectors_from_trade_board(trade_board):
    lookup = {item["symbol"]: item for item in trade_board}
    sector_map = [
        ("Semiconductor", ["NVDA", "SOXX"]),
        ("Mega Tech", ["AAPL", "MSFT", "QQQ"]),
        ("EV", ["TSLA"]),
        ("Dividend", ["SCHD"]),
        ("Bond", ["TLT"]),
    ]
    sectors = []
    for name, symbols in sector_map:
        changes = []
        for symbol in symbols:
            change = lookup.get(symbol, {}).get("change", "0%").replace("%", "")
            try:
                changes.append(float(change))
            except ValueError:
                changes.append(0)
        avg = sum(changes) / len(changes)
        tone = "up" if avg >= 0.25 else "down" if avg <= -0.25 else "flat"
        sectors.append({"name": name, "change": f"{avg:+.2f}%", "tone": tone})
    return sectors


def _change_number(value):
    try:
        return float(str(value).replace("%", "").replace("+", "").replace(",", ""))
    except ValueError:
        return 0


def _rankings_from_trade_board(trade_board):
    ordered = sorted(trade_board, key=lambda item: abs(_change_number(item.get("change", "0"))), reverse=True)
    return [
        {
            "rank": index + 1,
            "symbol": item["symbol"],
            "name": item["name"],
            "price": item["price"],
            "change": item["change"],
            "tone": item["tone"],
            "signal": item["signal"],
        }
        for index, item in enumerate(ordered[:8])
    ]


def _market_news_sources():
    return [
        {
            "source": "Yahoo Finance",
            "title": "시장 가격, 지수, 종목 뉴스 확인",
            "summary": "글로벌 지수와 개별 종목 가격 흐름을 교차 확인하는 기준 소스입니다.",
            "url": "https://finance.yahoo.com/",
        },
        {
            "source": "Reuters Markets",
            "title": "글로벌 주식, 채권, 환율, 원자재 이슈",
            "summary": "매크로와 시장 위험 이벤트를 해석할 때 참고하는 뉴스 소스입니다.",
            "url": "https://www.reuters.com/markets/",
        },
        {
            "source": "CNBC Markets",
            "title": "미국장 실시간 흐름과 섹터 뉴스",
            "summary": "미국장 장중 이슈와 주요 종목 움직임을 보조 확인합니다.",
            "url": "https://www.cnbc.com/markets/",
        },
    ]


def _alerts_from_live(snapshot):
    alerts = []
    mood = snapshot["mood"]["state"]
    if mood == "Risk Off":
        alerts.append({"level": "watch", "title": "Risk Off", "message": "관심 종목 하락 비중이 높아 신규 진입보다 위험 관리가 우선입니다."})
    for item in snapshot["indices"]:
        if item["symbol"] in {"USD/KRW", "US10Y", "VIX"} and item["tone"] in {"warn", "up"}:
            alerts.append({"level": "watch", "title": item["symbol"], "message": f"{item['name']} 현재 {item['value']} / {item['change']} 입니다."})
    alerts.append({"level": "info", "title": "Live Data", "message": f"{snapshot['source']} 기준으로 {snapshot['refresh_seconds']}초 단위 갱신합니다."})
    return alerts[:3]


def build_report(report_type):
    source = REPORTS.get(report_type, REPORTS["morning"])
    report = dict(source)
    report["report_type"] = report_type
    report["generated_at"] = _now().isoformat()
    report["snapshot"] = market_snapshot()
    report["message"] = "\n".join(f"- {item}" for item in report["bullets"])
    report["sms_preview"] = (
        "[MarketFlow]\n"
        "오늘 시장: Risk On\n"
        "Nasdaq +1.6%, SOXX +2.1%, USD/KRW 1,360\n"
        "DC 참고: 성장 ETF 흐름은 양호하지만 반도체 과열은 주의"
    )
    report["kakao_preview"] = {
        "title": "오늘의 글로벌 시장 브리프",
        "summary": report["bullets"][:5],
        "buttons": ["대시보드 열기", "리밸런싱 보기", "위험 알림 보기"],
    }
    return report


def list_reports():
    return [
        {"report_type": key, "title": value["title"], "label": value["label"], "send_time": value["send_time"], "summary": value["summary"]}
        for key, value in REPORTS.items()
    ]
