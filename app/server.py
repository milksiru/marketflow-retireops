import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from app import db
from app.notifications import send_notification
from app.pipeline import (
    collect_market_data,
    generate_daily_report,
    latest_analysis,
    run_analysis,
    send_daily_report_sms,
    send_risk_alert_sms,
)
from app.reports import build_report, list_reports, market_snapshot
from app.sms import send_sms


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._html()
        if path == "/healthz":
            return self._json({"ok": True})
        if path == "/api/dashboard":
            return self._json(market_snapshot())
        if path == "/api/reports":
            return self._json({"reports": list_reports()})
        if path == "/api/analyze/latest":
            return self._json(latest_analysis())
        if path == "/api/market-score/latest":
            return self._json({"market_score": db.latest_market_score()})
        if path == "/api/signals/latest":
            return self._json({"signals": db.latest_asset_signals()})
        if path == "/api/reports/daily/latest":
            return self._json({"daily_report": db.latest_daily_report()})
        if path.startswith("/api/reports/"):
            return self._json(build_report(path.rsplit("/", 1)[-1]))
        if path == "/api/notifications":
            return self._json({"logs": db.list_logs()})
        if path == "/api/notifications/logs":
            return self._json({"logs": db.list_logs()})
        if path == "/api/notifications/stats":
            return self._json(db.notification_stats())
        if path == "/api/notifications/channels":
            return self._json({"channels": db.list_channels()})
        if path == "/api/subscriptions":
            return self._json({"subscriptions": db.list_subscriptions()})
        if path == "/api/family-plan":
            return self._json({"family_plan": market_snapshot()["family_plan"]})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        payload = self._read_json()
        if path == "/api/notifications/test":
            channel = payload.get("channel", "sms")
            recipient = payload.get("recipient", "test-recipient")
            report_type = payload.get("report_type", "morning")
            return self._json(send_notification(channel, recipient, report_type))
        if path == "/api/analyze/run":
            provider = payload.get("provider", "mock")
            collected = collect_market_data(provider)
            analyzed = run_analysis()
            report = generate_daily_report()
            return self._json({"collector": collected, "analysis": analyzed, "report": report})
        if path == "/api/reports/daily/send-sms":
            return self._json(send_daily_report_sms())
        if path == "/api/notifications/sms/test":
            recipient = payload.get("recipient")
            return self._json(send_sms("MarketFlow SMS Test", "문자 알림은 투자 참고 정보를 전달합니다. 자동 매수/매도 기능은 제공하지 않습니다.", recipient, "sms-test"))
        if path == "/api/notifications/sms/send":
            return self._json(
                send_sms(
                    payload.get("title", "MarketFlow"),
                    payload.get("message", "MarketFlow notification"),
                    payload.get("recipient"),
                    payload.get("report_type", "manual"),
                )
            )
        if path == "/api/notifications/sms/risk-alert":
            return self._json(send_risk_alert_sms())
        if path == "/api/notifications/send":
            return self._json(
                send_notification(
                    payload.get("channel", "sms"),
                    payload.get("recipient", "test-recipient"),
                    payload.get("report_type", "morning"),
                    payload.get("title"),
                    payload.get("message"),
                )
            )
        if path == "/api/subscriptions":
            subscription_id = db.upsert_subscription(payload)
            return self._json({"status": "saved", "id": subscription_id})
        if path == "/api/family-plan":
            updated = db.update_family_plan_settings(payload)
            return self._json({"status": "saved", "updated": updated, "family_plan": market_snapshot()["family_plan"]})
        return self._json({"error": "not found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/notifications/channels/") and path.endswith("/settings"):
            channel = path.split("/")[-2]
            try:
                db.update_channel(channel, self._read_json())
                return self._json({"status": "updated"})
            except KeyError:
                return self._json({"error": "unknown channel"}, 404)
        return self._json({"error": "not found"}, 404)

    def _html(self):
        html = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MarketFlow RetireOps</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa; --panel: #ffffff; --panel2: #f2f4f6; --line: #e5e8eb;
      --text: #191f28; --muted: #8b95a1; --soft: #4e5968; --up: #f04452;
      --down: #3182f6; --warn: #f59f00; --blue: #3182f6; --green: #00a86b;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; background: var(--bg); color: var(--text); }
    .shell { display: grid; grid-template-columns: 188px minmax(0, 1fr); min-height: 100vh; }
    aside { border-right: 1px solid var(--line); padding: 22px 14px 48px; background: rgba(255,255,255,.86); position: sticky; top: 0; height: 100dvh; overflow-y: auto; scrollbar-gutter: stable; backdrop-filter: blur(14px); }
    .brand { display: block; width: calc(100% - 16px); border: 0; background: transparent; padding: 0; font: inherit; font-weight: 850; font-size: 18px; margin: 2px 8px 22px; color: var(--text); text-align: left; cursor: pointer; }
    .brand:hover { color: var(--blue); }
    nav button { display: block; width: 100%; margin: 3px 0; padding: 11px 12px; border: 0; border-radius: 8px; text-align: left; color: var(--soft); background: transparent; cursor: pointer; font-weight: 700; }
    nav button.active, nav button:hover { background: #eef6ff; color: var(--blue); }
    main { padding: 26px 28px 92px; max-width: 1060px; width: 100%; margin: 0 auto; }
    header { display: flex; justify-content: space-between; gap: 18px; align-items: start; margin-bottom: 18px; }
    .header-actions { display: flex; align-items: stretch; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .clock { min-width: 306px; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 13px 14px; box-shadow: 0 8px 24px rgba(25,31,40,.05); }
    .clock-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .clock-date { color: var(--soft); font-size: 12px; font-weight: 700; }
    .live { display: inline-flex; align-items: center; gap: 5px; color: var(--green); font-size: 11px; font-weight: 850; letter-spacing: 0; }
    .live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--green); }
    .clock-time { font-size: 32px; font-weight: 900; margin-top: 2px; font-variant-numeric: tabular-nums; letter-spacing: 0; }
    .clock-meta { color: var(--blue); font-size: 12px; font-weight: 800; margin-top: 4px; }
    .source-meta { color: var(--muted); font-size: 11px; margin-top: 3px; }
    .sessions { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 10px; }
    .session { background: var(--panel2); border: 1px solid transparent; border-radius: 8px; padding: 7px; min-height: 50px; }
    .session b { display: block; font-size: 11px; color: var(--soft); }
    .session span { display: block; margin-top: 3px; font-size: 11px; color: var(--muted); }
    .session.open { background: #ecfdf5; border-color: #bbf7d0; }
    .session.open b, .session.open span { color: var(--green); }
    h1 { margin: 0; font-size: 30px; line-height: 1.22; font-weight: 900; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 17px; font-weight: 850; }
    h3 { margin: 0 0 6px; font-size: 15px; font-weight: 850; }
    p { margin: 0; }
    .muted { color: var(--muted); line-height: 1.55; }
    .grid { display: grid; gap: 12px; }
    .top { grid-template-columns: 1.25fr .75fr; }
    .cards { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .two { grid-template-columns: 1fr 1fr; }
    .card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 17px; min-width: 0; box-shadow: 0 8px 24px rgba(25,31,40,.04); }
    .mood { display: grid; grid-template-columns: 96px 1fr; gap: 16px; align-items: center; }
    .score { width: 88px; height: 88px; border-radius: 8px; display: grid; place-items: center; background: #eef6ff; color: var(--blue); }
    .score b { display: grid; place-items: center; width: 100%; height: 100%; font-size: 30px; font-weight: 950; }
    .badge { display: inline-flex; align-items: center; min-height: 26px; padding: 4px 9px; border-radius: 999px; background: #eef6ff; color: var(--blue); font-size: 12px; font-weight: 750; margin: 5px 5px 0 0; }
    .ticker { display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 10px; }
    .tile { background: var(--panel2); border: 1px solid transparent; border-radius: 8px; padding: 13px; min-height: 92px; }
    .market-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .market-tile { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; min-height: 152px; overflow: hidden; }
    .market-head { display: flex; justify-content: space-between; gap: 8px; align-items: start; }
    .market-symbol { font-size: 18px; font-weight: 900; }
    .price { font-size: 28px; font-weight: 950; margin-top: 7px; font-variant-numeric: tabular-nums; }
    .spark { width: 100%; height: 42px; margin-top: 9px; }
    .mini-meta { display: flex; justify-content: space-between; gap: 8px; margin-top: 8px; font-size: 12px; color: var(--muted); }
    .index-strip { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(138px, 1fr); gap: 8px; overflow-x: auto; padding-bottom: 2px; }
    .index-chip { min-height: 90px; background: var(--panel2); border: 1px solid transparent; border-radius: 8px; padding: 11px; }
    .value { font-size: 22px; font-weight: 900; margin: 4px 0; font-variant-numeric: tabular-nums; }
    .up { color: var(--up); } .down { color: var(--down); } .warn { color: var(--warn); } .flat { color: var(--muted); }
    .list { display: grid; gap: 10px; }
    .row { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }
    .row:last-child { border-bottom: 0; }
    .bar { height: 7px; border-radius: 999px; background: #edf1f5; overflow: hidden; margin-top: 8px; }
    .bar span { display: block; height: 100%; background: var(--blue); }
    .heat { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
    .heat div { min-height: 72px; border-radius: 8px; padding: 10px; background: var(--panel2); border: 1px solid transparent; }
    .report-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .report-tabs button, .primary, select, input { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px; padding: 10px 12px; font-weight: 750; }
    .report-tabs button.active, .primary { background: var(--blue); border-color: var(--blue); color: #fff; cursor: pointer; }
    pre { white-space: pre-wrap; margin: 0; line-height: 1.5; color: var(--soft); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
    .channels { grid-template-columns: repeat(5, minmax(140px, 1fr)); }
    .switch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; background: var(--muted); }
    .switch.on { background: var(--green); }
    .mobilebar { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: rgba(255,255,255,.94); border-top: 1px solid var(--line); grid-template-columns: repeat(5, 1fr); z-index: 5; backdrop-filter: blur(14px); }
    .mobilebar button { border: 0; background: transparent; color: var(--muted); padding: 12px 6px; font-weight: 800; }
    .mobilebar button.active { color: var(--blue); }
    section { display: none; }
    section.active { display: block; }
    @media (max-width: 980px) {
      .shell { display: block; }
      aside { display: none; }
      main { padding: 18px 14px 82px; }
      header { display: block; }
      .header-actions { justify-content: stretch; margin-top: 13px; }
      .clock, .primary { width: 100%; }
      .top, .two, .cards, .channels { grid-template-columns: 1fr; }
      .ticker, .market-grid { grid-template-columns: 1fr; }
      .mood { grid-template-columns: 1fr; }
      .score { width: 100%; height: 76px; }
      .heat { grid-template-columns: repeat(2, 1fr); }
      .mobilebar { display: grid; }
    }
    .shell { grid-template-columns: 172px minmax(0, 1fr); }
    aside { background: #fff; }
    .brand { line-height: 1.35; }
    .family-plan { margin-top: 18px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #f8fafc; }
    .family-plan h3 { font-size: 14px; margin-bottom: 8px; }
    .plan-target { display: inline-flex; padding: 5px 8px; border-radius: 999px; background: #eef6ff; color: var(--blue); font-size: 12px; font-weight: 900; margin-bottom: 9px; }
    .plan-summary { color: var(--soft); font-size: 12px; line-height: 1.5; margin-bottom: 10px; }
    .plan-mini { display: grid; gap: 6px; margin-top: 8px; }
    .plan-line { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
    .plan-line span:first-child { color: var(--muted); }
    .plan-line b { font-variant-numeric: tabular-nums; text-align: right; }
    .plan-goal { margin-top: 10px; }
    .plan-goal-top { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; font-weight: 850; }
    .plan-goal small { display: block; color: var(--muted); margin-top: 4px; line-height: 1.4; }
    .plan-note { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); color: var(--muted); font-size: 11px; line-height: 1.45; }
    main { max-width: 1380px; padding-top: 20px; }
    header { align-items: center; min-height: 64px; }
    .header-copy p { max-width: 560px; }
    .page-kicker { color: var(--blue); font-size: 13px; font-weight: 850; margin-bottom: 6px; }
    .dashboard-shell { display: grid; grid-template-columns: minmax(0, 1fr) 318px; gap: 16px; align-items: start; }
    .main-board { display: grid; gap: 14px; min-width: 0; }
    .right-rail { display: grid; gap: 14px; position: sticky; top: 16px; min-width: 0; }
    .market-overview { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 12px; }
    .hero-mood { min-height: 236px; background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); }
    .hero-mood .mood { grid-template-columns: 116px 1fr; }
    .hero-mood .score { width: 104px; height: 104px; background: #f0f6ff; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
    .section-head .muted { font-size: 12px; }
    .quote-table { display: grid; gap: 2px; }
    .quote-row, .asset-row, .rank-row, .news-row { display: grid; align-items: center; border-radius: 8px; min-width: 0; }
    .quote-row { grid-template-columns: 1.2fr .9fr .75fr .6fr; gap: 10px; padding: 11px 12px; }
    .quote-row:hover, .asset-row:hover, .rank-row:hover { background: #f7f9fc; }
    .quote-head, .asset-head { color: var(--muted); font-size: 12px; font-weight: 800; }
    .asset-table { display: grid; gap: 4px; }
    .asset-row { grid-template-columns: 1.1fr .85fr .75fr 1.05fr; gap: 12px; padding: 12px; border-top: 1px solid var(--line); }
    .asset-name { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .avatar { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; background: #eef3f8; color: var(--soft); font-size: 11px; font-weight: 900; }
    .asset-symbol { font-weight: 900; }
    .asset-sub { color: var(--muted); font-size: 13px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .asset-price { font-size: 20px; font-weight: 900; font-variant-numeric: tabular-nums; text-align: right; }
    .asset-change { font-weight: 850; text-align: right; }
    .tiny-spark { min-width: 112px; }
    .rank-row { grid-template-columns: 26px 1fr auto; gap: 9px; padding: 10px 0; border-bottom: 1px solid var(--line); }
    .rank-row:last-child, .news-row:last-child { border-bottom: 0; }
    .rank-num { color: var(--blue); font-weight: 900; }
    .news-row { gap: 5px; padding: 12px 0; border-bottom: 1px solid var(--line); }
    .news-source { color: var(--blue); font-size: 12px; font-weight: 850; }
    .news-link { color: var(--text); text-decoration: none; font-weight: 850; line-height: 1.35; }
    .news-link:hover { color: var(--blue); }
    .detail-link { color: var(--blue); text-decoration: none; font-size: 12px; font-weight: 850; }
    .step-list { display: grid; gap: 10px; }
    .step-item { padding: 10px 0; border-bottom: 1px solid var(--line); color: var(--soft); line-height: 1.55; font-size: 13px; }
    .step-item:last-child { border-bottom: 0; }
    .finance-grid { display: grid; grid-template-columns: 1.15fr .85fr; gap: 14px; align-items: start; }
    .money-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .money-card { background: var(--panel2); border-radius: 8px; padding: 14px; min-height: 92px; }
    .money-card span { color: var(--muted); font-size: 12px; font-weight: 800; }
    .money-card b { display: block; margin-top: 8px; font-size: 22px; font-weight: 950; font-variant-numeric: tabular-nums; }
    .finance-list { display: grid; gap: 6px; }
    .finance-list .row { padding: 10px 0; }
    .edit-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .edit-field { display: grid; gap: 6px; }
    .edit-field label { color: var(--muted); font-size: 12px; font-weight: 850; }
    .edit-field input { width: 100%; font-variant-numeric: tabular-nums; }
    .save-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px; }
    .save-state { color: var(--muted); font-size: 12px; }
    .brief-card .row { align-items: start; }
    .brief-no { flex: 0 0 auto; width: 22px; height: 22px; border-radius: 7px; display: grid; place-items: center; background: #eef6ff; color: var(--blue); font-size: 12px; font-weight: 900; }
    .risk-pill { display: inline-flex; align-items: center; justify-content: center; min-width: 46px; height: 26px; border-radius: 999px; background: #eef6ff; color: var(--blue); font-weight: 900; font-size: 12px; }
    .clock { min-width: 270px; box-shadow: none; }
    .sessions { display: none; }
    .primary { box-shadow: 0 8px 18px rgba(49,130,246,.2); }
    @media (max-width: 1180px) {
      .dashboard-shell { grid-template-columns: 1fr; }
      .right-rail { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .right-rail .card:first-child { grid-row: span 2; }
    }
    @media (max-width: 980px) {
      .market-overview, .right-rail { grid-template-columns: 1fr; }
      .quote-row { grid-template-columns: 1.2fr .8fr .65fr; }
      .quote-row span:nth-child(4), .quote-row .mini-meta { display: none; }
      .asset-row { grid-template-columns: 1fr auto; }
      .asset-row .asset-price { text-align: left; }
      .asset-row .tiny-spark { grid-column: 1 / -1; }
      .hero-mood .mood { grid-template-columns: 1fr; }
      .finance-grid, .money-grid, .edit-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <button class="brand" onclick="goHome()">MarketFlow RetireOps</button>
      <nav id="sideNav"></nav>
    </aside>
    <main>
      <header>
        <div class="header-copy">
          <div class="page-kicker">MarketFlow Live Desk</div>
          <h1>오늘의 시장 흐름</h1>
          <p class="muted">시장 데이터, 관심 ETF, DC 운용 참고와 뉴스 근거를 한 화면에서 확인합니다.</p>
        </div>
        <div class="header-actions">
          <div class="clock">
            <div class="clock-top"><div class="clock-date" id="clockDate">KST</div><div class="live">LIVE</div></div>
            <div class="clock-time" id="clockTime">--:--:--</div>
            <div class="clock-meta" id="dataAsOf">데이터 기준 확인 중</div>
            <div class="source-meta" id="sourceMeta">실시간 수집 대기</div>
            <div class="sessions" id="sessions"></div>
          </div>
          <button class="primary" onclick="sendTest()">SMS 테스트 발송</button>
        </div>
      </header>
      <section id="dashboard" class="active">
        <div class="dashboard-shell">
          <div class="main-board">
            <div class="market-overview">
              <div class="card hero-mood"><div class="section-head"><h2>시장 상태</h2><span class="muted">실시간 데이터 기반</span></div><div id="mood" class="mood"></div></div>
              <div class="card brief-card"><div class="section-head"><h2>오늘의 체크포인트</h2><span class="muted">요약</span></div><div id="brief" class="list"></div></div>
            </div>
            <div class="card"><div class="section-head"><h2>글로벌 마켓</h2><span class="muted">지수 / 금리 / 환율 / 변동성</span></div><div id="indices" class="quote-table"></div></div>
            <div class="card"><div class="section-head"><h2>주요 종목 모니터</h2><span class="muted">가격, 변동률, 신호</span></div><div id="tradeBoard" class="asset-table"></div></div>
            <div class="grid two">
              <div class="card"><h2>관심 ETF</h2><div id="watchlist" class="list"></div></div>
              <div class="card"><h2>DC 퇴직연금</h2><div id="dc"></div></div>
            </div>
            <div class="grid two">
              <div class="card"><h2>섹터 흐름</h2><div id="sectors" class="heat"></div></div>
              <div class="card"><h2>위험 알림</h2><div id="alerts" class="list"></div></div>
            </div>
          </div>
          <div class="right-rail">
            <div class="card"><div class="section-head"><h2>실시간 랭킹</h2><span class="muted">변동률 기준</span></div><div id="ranking" class="list"></div></div>
            <div class="card"><div class="section-head"><h2>가족 실행 플랜</h2><span class="muted">주택 목표</span></div><div id="familySteps" class="step-list"></div></div>
            <div class="card"><div class="section-head"><h2>뉴스 근거</h2><span class="muted">출처와 링크</span></div><div id="newsRefs" class="list"></div></div>
            <div class="card"><h2>데이터 메모</h2><p class="muted">표시된 분석은 투자 참고 신호이며 자동 매수/매도 판단이 아닙니다.</p></div>
          </div>
        </div>
      </section>
      <section id="reports">
        <div class="card"><h2>Reports</h2><div id="reportTabs" class="report-tabs"></div><div id="reportView"></div></div>
      </section>
      <section id="family">
        <div class="finance-grid">
          <div class="grid">
            <div class="card"><div class="section-head"><h2>우리 가족 자금 상황</h2><span class="muted">주택 매매 목표</span></div><div id="familyOverview"></div></div>
            <div class="card"><div class="section-head"><h2>금액 수정</h2><span class="muted">저장 즉시 반영</span></div><div id="familyEditor" class="edit-grid"></div><div class="save-row"><span id="familySaveState" class="save-state">금액을 수정한 뒤 저장하세요.</span><button class="primary" onclick="saveFamilyPlan()">저장</button></div></div>
            <div class="card"><h2>목표 진행률</h2><div id="familyGoalsPage" class="list"></div></div>
            <div class="card"><h2>실행 순서</h2><div id="familyStepsPage" class="step-list"></div></div>
          </div>
          <div class="grid">
            <div class="card"><h2>자산</h2><div id="familyAssets" class="finance-list"></div></div>
            <div class="card"><h2>부채</h2><div id="familyDebts" class="finance-list"></div></div>
          </div>
        </div>
      </section>
      <section id="notifications">
        <div class="grid cards" id="stats"></div>
        <div class="card" style="margin-top:14px"><h2>Notification Channels</h2><div id="channels" class="grid channels"></div></div>
        <div class="card" style="margin-top:14px"><h2>Notification Logs</h2><div id="logs" class="list"></div></div>
      </section>
      <section id="settings">
        <div class="card"><h2>Report Subscription</h2>
          <div class="grid two">
            <select id="subReport"><option value="morning">Morning</option><option value="market-open">Market Open</option><option value="evening">Evening</option><option value="weekly">Weekly</option><option value="monthly-dc">Monthly DC</option></select>
            <select id="subChannel"><option value="sms">SMS</option><option value="kakao">Kakao</option><option value="email">Email</option><option value="telegram">Telegram</option><option value="teams">Teams</option></select>
            <input id="subRecipient" placeholder="recipient" value="scheduled-recipient">
            <input id="subTime" placeholder="send time" value="07:30">
          </div>
          <p style="margin-top:12px"><button class="primary" onclick="saveSubscription()">구독 저장</button></p>
          <div id="subscriptions" class="list" style="margin-top:12px"></div>
        </div>
        <div class="card" style="margin-top:14px"><h2>SMS Notification</h2>
          <p class="muted">문자 알림은 투자 참고 정보를 전달합니다. 자동 매수/매도 기능은 제공하지 않습니다.</p>
          <p class="muted">SMS Provider 설정 전에는 Mock 모드로만 동작합니다.</p>
          <div class="grid two" style="margin-top:12px">
            <select id="smsProvider"><option value="mock">mock</option><option value="solapi">solapi</option><option value="sens">sens</option></select>
            <input id="smsRecipient" placeholder="01012345678" value="01000000000">
          </div>
          <p style="margin-top:12px"><button class="primary" onclick="sendSmsTest()">테스트 문자 발송</button></p>
        </div>
      </section>
    </main>
  </div>
  <div class="mobilebar" id="mobileNav"></div>
  <script>
    const views = [["dashboard","홈"],["reports","리포트"],["notifications","알림"],["settings","설정"],["family","가족 플랜"]];
    const toneClass = t => t === "up" ? "up" : t === "down" ? "down" : t === "warn" ? "warn" : "flat";
    function formatKst(value, options) {
      return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", ...options }).format(value);
    }
    function minutesInZone(zone) {
      const parts = new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date());
      const hour = Number(parts.find(p => p.type === "hour").value);
      const minute = Number(parts.find(p => p.type === "minute").value);
      return hour * 60 + minute;
    }
    function sessionState(name, zone, open, close) {
      const now = minutesInZone(zone);
      const active = now >= open && now < close;
      const left = active ? close - now : (now < open ? open - now : 1440 - now + open);
      const h = Math.floor(left / 60);
      const m = left % 60;
      return { name, active, label: active ? `OPEN ${h}h ${m}m left` : `CLOSED ${h}h ${m}m` };
    }
    function renderSessions() {
      const sessions = [
        sessionState("KR", "Asia/Seoul", 9 * 60, 15 * 60 + 30),
        sessionState("JP", "Asia/Tokyo", 9 * 60, 15 * 60),
        sessionState("LDN", "Europe/London", 8 * 60, 16 * 60 + 30),
        sessionState("NY", "America/New_York", 9 * 60 + 30, 16 * 60),
      ];
      document.getElementById("sessions").innerHTML = sessions.map(s => `<div class="session ${s.active ? "open" : ""}"><b>${s.name}</b><span>${s.label}</span></div>`).join("");
    }
    function tickClock() {
      const now = new Date();
      document.getElementById("clockDate").textContent = formatKst(now, { year: "numeric", month: "long", day: "numeric", weekday: "long" });
      document.getElementById("clockTime").textContent = formatKst(now, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
      renderSessions();
    }
    function setDataAsOf(value, source, cacheStatus, refreshSeconds) {
      const asOf = value ? new Date(value) : new Date();
      document.getElementById("dataAsOf").textContent = `데이터 기준 ${formatKst(asOf, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
      document.getElementById("sourceMeta").textContent = `${source || "unknown"} / ${cacheStatus || "checking"} / ${refreshSeconds || 30}초 갱신`;
    }
    function nav(target) {
      document.querySelectorAll("section").forEach(s => s.classList.toggle("active", s.id === target));
      document.querySelectorAll("[data-nav]").forEach(b => b.classList.toggle("active", b.dataset.nav === target));
    }
    async function goHome() {
      nav("dashboard");
      await loadDashboard();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    function renderNav() {
      for (const mount of [document.getElementById("sideNav"), document.getElementById("mobileNav")]) {
        mount.innerHTML = views.map(([id,label]) => `<button data-nav="${id}" onclick="nav('${id}')">${label}</button>`).join("");
      }
      document.querySelectorAll('[data-nav="dashboard"]').forEach(b => b.classList.add("active"));
    }
    function spark(points, tone) {
      const max = Math.max(...points);
      const min = Math.min(...points);
      const range = Math.max(1, max - min);
      const coords = points.map((p, idx) => {
        const x = idx * (100 / (points.length - 1));
        const y = 38 - ((p - min) / range) * 32;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      const color = tone === "down" ? "#3182f6" : tone === "warn" ? "#f59f00" : tone === "flat" ? "#8b95a1" : "#f04452";
      return `<svg class="spark" viewBox="0 0 100 42" preserveAspectRatio="none" aria-hidden="true"><polyline points="${coords}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><line x1="0" y1="39" x2="100" y2="39" stroke="#e5e8eb" stroke-width="1"/></svg>`;
    }
    function miniSpark(points, tone) {
      return spark(points, tone).replace('class="spark"', 'class="spark tiny-spark"');
    }
    function formatWon(value) {
      return new Intl.NumberFormat("ko-KR").format(Number(value || 0));
    }
    function parseWon(value) {
      return Number(String(value || "").replace(/[^\\d]/g, "")) || 0;
    }
    function renderFamilyPlan(plan) {
      if (!plan) return;
      const goalHtml = plan.goals.map(g => {
        const pct = Math.max(4, Math.min(100, Math.round((g.current / g.target) * 100)));
        return `<div class="plan-goal"><div class="plan-goal-top"><span>${g.label}</span><span>${pct}%</span></div><div class="bar"><span style="width:${pct}%"></span></div><small>${g.caption}</small></div>`;
      }).join("");
      const sidePlan = document.getElementById("familyPlan");
      if (sidePlan) sidePlan.innerHTML = `<h3>${plan.title}</h3><div class="plan-target">${plan.target}</div><p class="plan-summary">${plan.summary}</p><div class="plan-mini">${plan.metrics.map(m => `<div class="plan-line"><span>${m.label}</span><b>${m.value}</b></div>`).join("")}</div>${goalHtml}<div class="plan-note">월 예적금 ${plan.monthly_saving} 기준. 세금, 대출한도, 금리는 계약 전 별도 확인 필요.</div>`;
      const steps = document.getElementById("familySteps");
      if (steps) steps.innerHTML = plan.steps.map(s => `<div class="step-item">${s}</div>`).join("");
      const overview = document.getElementById("familyOverview");
      if (overview) overview.innerHTML = `<div class="money-grid">${plan.metrics.map(m => `<div class="money-card"><span>${m.label}</span><b>${m.value}</b></div>`).join("")}</div><p class="muted" style="margin-top:14px">${plan.summary}</p>`;
      const assets = document.getElementById("familyAssets");
      if (assets) assets.innerHTML = plan.assets.map(a => `<div class="row"><span>${a.label}</span><b>${a.value}</b></div>`).join("");
      const debts = document.getElementById("familyDebts");
      if (debts) debts.innerHTML = plan.debts.map(d => `<div class="row"><span>${d.label}</span><b class="warn">${d.value}</b></div>`).join("");
      const familyGoals = document.getElementById("familyGoalsPage");
      if (familyGoals) familyGoals.innerHTML = goalHtml;
      const familySteps = document.getElementById("familyStepsPage");
      if (familySteps) familySteps.innerHTML = plan.steps.map(s => `<div class="step-item">${s}</div>`).join("");
      const editor = document.getElementById("familyEditor");
      if (editor && !editor.contains(document.activeElement)) {
        editor.innerHTML = plan.editable.map(item => `<div class="edit-field"><label>${item.label}</label><input data-family-key="${item.key}" value="${formatWon(item.value)}" inputmode="numeric" oninput="this.value = formatWon(parseWon(this.value))"></div>`).join("");
      }
    }
    async function loadDashboard() {
      const data = await fetch("/api/dashboard").then(r => r.json());
      setDataAsOf(data.as_of, data.source, data.cache_status, data.refresh_seconds);
      renderFamilyPlan(data.family_plan);
      document.getElementById("mood").innerHTML = `<div class="score"><b>${data.mood.score}</b></div><div><h3>${data.mood.state}</h3><p class="muted">${data.mood.plain}</p><p>${data.badges.map(b => `<span class="badge">${b}</span>`).join("")}</p><div class="list">${data.mood.drivers.map(d => `<div class="row"><span>${d}</span><span class="risk-pill">확인</span></div>`).join("")}</div></div>`;
      document.getElementById("brief").innerHTML = data.brief.map((b,i) => `<div class="row"><span class="brief-no">${i + 1}</span><span>${b}</span></div>`).join("");
      document.getElementById("indices").innerHTML = `<div class="quote-row quote-head"><span>자산</span><span>현재</span><span>변동</span><span>구분</span></div>` + data.indices.map(i => `<div class="quote-row"><span><b>${i.symbol}</b><br><span class="asset-sub">${i.name}</span></span><span class="value">${i.value}</span><span class="${toneClass(i.tone)}"><b>${i.change}</b></span><span class="mini-meta">${i.session} / ${i.volume}</span></div>`).join("");
      document.getElementById("tradeBoard").innerHTML = `<div class="asset-row asset-head"><span>종목</span><span>현재가</span><span>등락률</span><span>흐름</span></div>` + data.trade_board.map(t => `<div class="asset-row"><div class="asset-name"><span class="avatar">${t.symbol.slice(0,2)}</span><span><span class="asset-symbol">${t.symbol}</span><br><span class="asset-sub">${t.name} · ${t.signal}</span></span></div><div class="asset-price">${t.price}</div><div class="asset-change ${toneClass(t.tone)}">${t.change}</div>${miniSpark(t.spark, t.tone)}</div>`).join("");
      document.getElementById("watchlist").innerHTML = data.watchlist.map(w => `<div><div class="row"><span><b>${w.symbol}</b> <span class="muted">${w.name}</span><br><span>${w.signal}</span></span><span class="${w.change && w.change.startsWith('-') ? 'down' : 'up'}">${w.change || ''}</span></div><div class="mini-meta"><span>${w.risk}</span><span>Signal ${w.score}</span></div><div class="bar"><span style="width:${w.score}%"></span></div></div>`).join("");
      document.getElementById("dc").innerHTML = `<h3>${data.dc.style}</h3><p class="muted">${data.dc.plain_language}</p><div class="list" style="margin-top:12px">${data.dc.allocation.map(a => `<div><div class="row"><span>${a.label}</span><span>현재 ${a.current}% / 목표 ${a.target}%</span></div><div class="bar"><span style="width:${a.current}%"></span></div></div>`).join("")}</div><p class="badge">Risk Score ${data.dc.risk_score}</p><p class="muted" style="margin-top:10px">${data.dc.rebalance}</p>`;
      document.getElementById("sectors").innerHTML = data.sectors.map(s => `<div><b>${s.name}</b><p class="${toneClass(s.tone)}">${s.change}</p></div>`).join("");
      document.getElementById("alerts").innerHTML = data.alerts.map(a => `<div class="row"><span><b>${a.title}</b><br><span class="muted">${a.message}</span></span><span class="badge">${a.level}</span></div>`).join("");
      document.getElementById("ranking").innerHTML = (data.rankings || []).map(r => `<div class="rank-row"><span class="rank-num">${r.rank}</span><span><b>${r.symbol}</b><br><span class="asset-sub">${r.name}</span></span><span class="${toneClass(r.tone)}"><b>${r.change}</b></span></div>`).join("");
      document.getElementById("newsRefs").innerHTML = (data.news_sources || []).map(n => `<div class="news-row"><span class="news-source">${n.source}</span><a class="news-link" href="${n.url}" target="_blank" rel="noreferrer">${n.title}</a><p class="muted">${n.summary}</p><a class="detail-link" href="${n.url}" target="_blank" rel="noreferrer">자세히 보기</a></div>`).join("");
    }
    async function loadReports(type="morning") {
      const list = await fetch("/api/reports").then(r => r.json());
      document.getElementById("reportTabs").innerHTML = list.reports.map(r => `<button class="${r.report_type === type ? "active" : ""}" onclick="loadReports('${r.report_type}')">${r.label}</button>`).join("");
      const report = await fetch(`/api/reports/${type}`).then(r => r.json());
      document.getElementById("reportView").innerHTML = `<h3>${report.title}</h3><p class="muted">${report.summary}</p><div class="grid two" style="margin-top:12px"><div class="tile"><h3>요약</h3>${report.bullets.map(b => `<p style="margin:8px 0">${b}</p>`).join("")}</div><div class="tile"><h3>SMS Preview</h3><pre>${report.sms_preview}</pre><h3 style="margin-top:14px">Kakao Buttons</h3>${report.kakao_preview.buttons.map(b => `<span class="badge">${b}</span>`).join("")}</div></div>`;
    }
    async function loadNotifications() {
      const stats = await fetch("/api/notifications/stats").then(r => r.json());
      document.getElementById("stats").innerHTML = Object.entries(stats).map(([k,v]) => `<div class="card"><p class="muted">${k.replaceAll("_"," ")}</p><div class="value">${v}</div></div>`).join("");
      const channels = await fetch("/api/notifications/channels").then(r => r.json());
      document.getElementById("channels").innerHTML = channels.channels.map(c => `<div class="tile"><h3><span class="switch ${c.enabled ? "on" : ""}"></span>${c.channel_type}</h3><p class="muted">${c.provider}</p><span class="badge">${c.enabled ? "enabled" : "disabled"}</span></div>`).join("");
      const logs = await fetch("/api/notifications").then(r => r.json());
      document.getElementById("logs").innerHTML = logs.logs.length ? logs.logs.slice(0,12).map(l => `<div class="row"><span><b>${l.title}</b><br><span class="muted">${l.channel_type} / ${l.recipient}</span></span><span class="${l.status === "sent" ? "up" : "down"}">${l.status}</span></div>`).join("") : `<p class="muted">아직 발송 로그가 없습니다.</p>`;
    }
    async function loadSubscriptions() {
      const data = await fetch("/api/subscriptions").then(r => r.json());
      document.getElementById("subscriptions").innerHTML = data.subscriptions.length ? data.subscriptions.map(s => `<div class="row"><span>${s.report_type} -> ${s.channel_type}<br><span class="muted">${s.recipient}</span></span><span>${s.send_time}</span></div>`).join("") : `<p class="muted">등록된 구독이 없습니다.</p>`;
    }
    async function sendTest() {
      await fetch("/api/notifications/test", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({channel:"sms", recipient:"010-0000-0000", report_type:"morning"})});
      await loadNotifications();
      nav("notifications");
    }
    async function saveSubscription() {
      await fetch("/api/subscriptions", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({report_type:subReport.value, channel_type:subChannel.value, recipient:subRecipient.value, send_time:subTime.value})});
      await loadSubscriptions();
    }
    async function saveFamilyPlan() {
      const values = {};
      document.querySelectorAll("[data-family-key]").forEach(input => values[input.dataset.familyKey] = parseWon(input.value));
      document.getElementById("familySaveState").textContent = "저장 중...";
      const result = await fetch("/api/family-plan", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({values})}).then(r => r.json());
      renderFamilyPlan(result.family_plan);
      await loadDashboard();
      document.getElementById("familySaveState").textContent = "저장 완료";
    }
    async function sendSmsTest() {
      await fetch("/api/notifications/sms/test", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({recipient:smsRecipient.value, provider:smsProvider.value})});
      await loadNotifications();
      nav("notifications");
    }
    renderNav(); tickClock(); setInterval(tickClock, 1000); loadDashboard(); setInterval(loadDashboard, 30000); loadReports(); loadNotifications(); loadSubscriptions();
  </script>
</body>
</html>"""
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    with db.connect():
        pass
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
