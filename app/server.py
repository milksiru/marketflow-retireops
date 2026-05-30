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
      color-scheme: dark;
      --bg: #090d14; --panel: #101723; --panel2: #151f2e; --line: #263346;
      --text: #f4f7fb; --muted: #9ba8bb; --up: #4ade80; --down: #fb7185;
      --warn: #fbbf24; --blue: #38bdf8; --violet: #a78bfa;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; background: var(--bg); color: var(--text); }
    .shell { display: grid; grid-template-columns: 232px 1fr; min-height: 100vh; }
    aside { border-right: 1px solid var(--line); padding: 22px 16px; background: #0c121c; position: sticky; top: 0; height: 100vh; }
    .brand { font-weight: 800; font-size: 19px; margin-bottom: 24px; }
    nav button { display: block; width: 100%; margin: 4px 0; padding: 11px 12px; border: 0; border-radius: 7px; text-align: left; color: var(--muted); background: transparent; cursor: pointer; }
    nav button.active, nav button:hover { background: var(--panel2); color: var(--text); }
    main { padding: 24px 28px 88px; max-width: 1400px; width: 100%; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: start; margin-bottom: 18px; }
    .header-actions { display: flex; align-items: stretch; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .clock { min-width: 292px; border: 1px solid #1f8fb0; background: linear-gradient(135deg, #0b1522, #0f2634); border-radius: 8px; padding: 10px 12px; box-shadow: inset 0 0 0 1px rgba(56,189,248,.08); }
    .clock-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .clock-date { color: var(--muted); font-size: 12px; }
    .live { display: inline-flex; align-items: center; gap: 5px; color: var(--up); font-size: 11px; font-weight: 800; letter-spacing: .08em; }
    .live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--up); box-shadow: 0 0 12px var(--up); }
    .clock-time { font-size: 30px; font-weight: 850; margin-top: 2px; font-variant-numeric: tabular-nums; letter-spacing: .04em; }
    .clock-meta { color: var(--blue); font-size: 12px; margin-top: 4px; }
    .source-meta { color: var(--muted); font-size: 11px; margin-top: 3px; }
    .sessions { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 9px; }
    .session { background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.08); border-radius: 6px; padding: 6px; min-height: 50px; }
    .session b { display: block; font-size: 11px; }
    .session span { display: block; margin-top: 3px; font-size: 11px; color: var(--muted); }
    .session.open { border-color: rgba(74,222,128,.45); }
    h1 { margin: 0; font-size: 28px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    h3 { margin: 0 0 6px; font-size: 15px; }
    p { margin: 0; }
    .muted { color: var(--muted); line-height: 1.55; }
    .grid { display: grid; gap: 14px; }
    .top { grid-template-columns: 1.35fr .85fr; }
    .cards { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .two { grid-template-columns: 1fr 1fr; }
    .card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-width: 0; }
    .mood { display: grid; grid-template-columns: 128px 1fr; gap: 18px; align-items: center; }
    .score { width: 118px; height: 118px; border-radius: 50%; display: grid; place-items: center; background: conic-gradient(var(--blue) 0 74%, #243044 74%); }
    .score b { display: grid; place-items: center; width: 86px; height: 86px; border-radius: 50%; background: var(--panel); font-size: 25px; }
    .badge { display: inline-flex; align-items: center; min-height: 26px; padding: 4px 9px; border-radius: 999px; background: #203047; color: #dbeafe; font-size: 12px; margin: 5px 5px 0 0; }
    .ticker { display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 10px; }
    .tile { background: var(--panel2); border: 1px solid var(--line); border-radius: 7px; padding: 12px; min-height: 92px; }
    .market-grid { display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 10px; }
    .market-tile { background: #0d1522; border: 1px solid var(--line); border-radius: 7px; padding: 12px; min-height: 142px; overflow: hidden; }
    .market-head { display: flex; justify-content: space-between; gap: 8px; align-items: start; }
    .market-symbol { font-size: 17px; font-weight: 850; }
    .price { font-size: 24px; font-weight: 850; margin-top: 8px; font-variant-numeric: tabular-nums; }
    .spark { width: 100%; height: 42px; margin-top: 10px; }
    .mini-meta { display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: var(--muted); }
    .index-strip { display: grid; grid-template-columns: repeat(8, minmax(130px, 1fr)); gap: 8px; overflow-x: auto; padding-bottom: 2px; }
    .index-chip { min-height: 86px; background: var(--panel2); border: 1px solid var(--line); border-radius: 7px; padding: 10px; }
    .value { font-size: 20px; font-weight: 750; margin: 4px 0; }
    .up { color: var(--up); } .down { color: var(--down); } .warn { color: var(--warn); } .flat { color: var(--muted); }
    .list { display: grid; gap: 10px; }
    .row { display: flex; justify-content: space-between; gap: 10px; padding: 11px 0; border-bottom: 1px solid var(--line); }
    .row:last-child { border-bottom: 0; }
    .bar { height: 8px; border-radius: 999px; background: #253145; overflow: hidden; margin-top: 8px; }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--blue), var(--up)); }
    .heat { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
    .heat div { min-height: 72px; border-radius: 7px; padding: 10px; background: var(--panel2); border: 1px solid var(--line); }
    .report-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .report-tabs button, .primary, select, input { border: 1px solid var(--line); background: var(--panel2); color: var(--text); border-radius: 7px; padding: 9px 11px; }
    .report-tabs button.active, .primary { background: #0e7490; border-color: #0891b2; cursor: pointer; }
    pre { white-space: pre-wrap; margin: 0; line-height: 1.5; color: #dbeafe; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
    .channels { grid-template-columns: repeat(5, minmax(140px, 1fr)); }
    .switch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; background: var(--muted); }
    .switch.on { background: var(--up); }
    .mobilebar { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #0c121c; border-top: 1px solid var(--line); grid-template-columns: repeat(5, 1fr); z-index: 5; }
    .mobilebar button { border: 0; background: transparent; color: var(--muted); padding: 11px 6px; }
    .mobilebar button.active { color: var(--text); }
    section { display: none; }
    section.active { display: block; }
    @media (max-width: 980px) {
      .shell { display: block; }
      aside { display: none; }
      main { padding: 18px 14px 78px; }
      header { display: block; }
      .header-actions { justify-content: stretch; margin-top: 12px; }
      .clock { width: 100%; }
      .top, .two, .cards, .channels { grid-template-columns: 1fr; }
      .ticker, .market-grid { grid-template-columns: 1fr; }
      .index-strip { grid-template-columns: repeat(8, minmax(132px, 1fr)); }
      .mood { grid-template-columns: 1fr; }
      .mobilebar { display: grid; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">MarketFlow RetireOps</div>
      <nav id="sideNav"></nav>
    </aside>
    <main>
      <header>
        <div>
          <h1>오늘의 시장 흐름</h1>
          <p class="muted">시장 상태, 관심 ETF, DC 운용 참고, 알림 발송 상태를 한 번에 확인합니다.</p>
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
        <div class="grid top">
          <div class="card"><h2>Market Mood</h2><div id="mood" class="mood"></div></div>
          <div class="card"><h2>Today Brief</h2><div id="brief" class="list"></div></div>
        </div>
        <div class="card" style="margin-top:14px"><h2>World Market Strip</h2><div id="indices" class="index-strip"></div></div>
        <div class="card" style="margin-top:14px"><h2>Trade Monitor</h2><div id="tradeBoard" class="market-grid"></div></div>
        <div class="grid two" style="margin-top:14px">
          <div class="card"><h2>My Watchlist</h2><div id="watchlist" class="list"></div></div>
          <div class="card"><h2>DC Retirement</h2><div id="dc"></div></div>
        </div>
        <div class="grid two" style="margin-top:14px">
          <div class="card"><h2>Sector Flow</h2><div id="sectors" class="heat"></div></div>
          <div class="card"><h2>Alert Preview</h2><div id="alerts" class="list"></div></div>
        </div>
      </section>
      <section id="reports">
        <div class="card"><h2>Reports</h2><div id="reportTabs" class="report-tabs"></div><div id="reportView"></div></div>
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
    const views = [["dashboard","홈"],["reports","리포트"],["notifications","알림"],["settings","설정"]];
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
      const color = tone === "down" ? "#fb7185" : tone === "warn" ? "#fbbf24" : tone === "flat" ? "#9ba8bb" : "#4ade80";
      return `<svg class="spark" viewBox="0 0 100 42" preserveAspectRatio="none" aria-hidden="true"><polyline points="${coords}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><line x1="0" y1="39" x2="100" y2="39" stroke="#263346" stroke-width="1"/></svg>`;
    }
    async function loadDashboard() {
      const data = await fetch("/api/dashboard").then(r => r.json());
      setDataAsOf(data.as_of, data.source, data.cache_status, data.refresh_seconds);
      document.getElementById("mood").innerHTML = `<div class="score"><b>${data.mood.score}</b></div><div><h3>${data.mood.state}</h3><p class="muted">${data.mood.plain}</p><p>${data.badges.map(b => `<span class="badge">${b}</span>`).join("")}</p><div class="list">${data.mood.drivers.map(d => `<div class="row"><span>${d}</span><span class="up">check</span></div>`).join("")}</div></div>`;
      document.getElementById("brief").innerHTML = data.brief.map((b,i) => `<div class="row"><span>${i + 1}. ${b}</span></div>`).join("");
      document.getElementById("indices").innerHTML = data.indices.map(i => `<div class="index-chip"><div class="market-head"><div><h3>${i.symbol}</h3><p class="muted">${i.name}</p></div><b class="${toneClass(i.tone)}">${i.change}</b></div><div class="value">${i.value}</div><div class="mini-meta"><span>${i.session}</span><span>${i.volume}</span></div></div>`).join("");
      document.getElementById("tradeBoard").innerHTML = data.trade_board.map(t => `<div class="market-tile"><div class="market-head"><div><div class="market-symbol">${t.symbol}</div><p class="muted">${t.name}</p></div><b class="${toneClass(t.tone)}">${t.change}</b></div><div class="price">${t.price}</div>${spark(t.spark, t.tone)}<div class="mini-meta"><span>${t.signal}</span><span>${t.tone.toUpperCase()}</span></div></div>`).join("");
      document.getElementById("watchlist").innerHTML = data.watchlist.map(w => `<div><div class="row"><span><b>${w.symbol}</b> <span class="muted">${w.name}</span><br><span>${w.signal}</span></span><span class="${w.change && w.change.startsWith('-') ? 'down' : 'up'}">${w.change || ''}</span></div><div class="mini-meta"><span>${w.risk}</span><span>Signal ${w.score}</span></div><div class="bar"><span style="width:${w.score}%"></span></div></div>`).join("");
      document.getElementById("dc").innerHTML = `<h3>${data.dc.style}</h3><p class="muted">${data.dc.plain_language}</p><div class="list" style="margin-top:12px">${data.dc.allocation.map(a => `<div><div class="row"><span>${a.label}</span><span>현재 ${a.current}% / 목표 ${a.target}%</span></div><div class="bar"><span style="width:${a.current}%"></span></div></div>`).join("")}</div><p class="badge">Risk Score ${data.dc.risk_score}</p><p class="muted" style="margin-top:10px">${data.dc.rebalance}</p>`;
      document.getElementById("sectors").innerHTML = data.sectors.map(s => `<div><b>${s.name}</b><p class="${toneClass(s.tone)}">${s.change}</p></div>`).join("");
      document.getElementById("alerts").innerHTML = data.alerts.map(a => `<div class="row"><span><b>${a.title}</b><br><span class="muted">${a.message}</span></span><span class="badge">${a.level}</span></div>`).join("");
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
