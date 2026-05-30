import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from app import db
from app.notifications import send_notification
from app.reports import build_report, list_reports, market_snapshot


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
        if path.startswith("/api/reports/"):
            return self._json(build_report(path.rsplit("/", 1)[-1]))
        if path == "/api/notifications":
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
    .ticker { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 10px; }
    .tile { background: var(--panel2); border: 1px solid var(--line); border-radius: 7px; padding: 12px; min-height: 92px; }
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
      .top, .two, .cards, .channels { grid-template-columns: 1fr; }
      .ticker { grid-template-columns: repeat(2, minmax(0, 1fr)); }
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
        <button class="primary" onclick="sendTest()">SMS 테스트 발송</button>
      </header>
      <section id="dashboard" class="active">
        <div class="grid top">
          <div class="card"><h2>Market Mood</h2><div id="mood" class="mood"></div></div>
          <div class="card"><h2>Today Brief</h2><div id="brief" class="list"></div></div>
        </div>
        <div class="card" style="margin-top:14px"><h2>Global Index</h2><div id="indices" class="ticker"></div></div>
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
      </section>
    </main>
  </div>
  <div class="mobilebar" id="mobileNav"></div>
  <script>
    const views = [["dashboard","홈"],["reports","리포트"],["notifications","알림"],["settings","설정"]];
    const toneClass = t => t === "up" ? "up" : t === "down" ? "down" : t === "warn" ? "warn" : "flat";
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
    async function loadDashboard() {
      const data = await fetch("/api/dashboard").then(r => r.json());
      document.getElementById("mood").innerHTML = `<div class="score"><b>${data.mood.score}</b></div><div><h3>${data.mood.state}</h3><p class="muted">${data.mood.plain}</p><p>${data.badges.map(b => `<span class="badge">${b}</span>`).join("")}</p><div class="list">${data.mood.drivers.map(d => `<div class="row"><span>${d}</span><span class="up">check</span></div>`).join("")}</div></div>`;
      document.getElementById("brief").innerHTML = data.brief.map((b,i) => `<div class="row"><span>${i + 1}. ${b}</span></div>`).join("");
      document.getElementById("indices").innerHTML = data.indices.map(i => `<div class="tile"><h3>${i.symbol}</h3><p class="muted">${i.name}</p><div class="value">${i.value}</div><b class="${toneClass(i.tone)}">${i.change}</b></div>`).join("");
      document.getElementById("watchlist").innerHTML = data.watchlist.map(w => `<div><div class="row"><span><b>${w.symbol}</b> <span class="muted">${w.name}</span><br><span>${w.signal}</span></span><span class="warn">${w.risk}</span></div><div class="bar"><span style="width:${w.score}%"></span></div></div>`).join("");
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
    renderNav(); loadDashboard(); loadReports(); loadNotifications(); loadSubscriptions();
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
