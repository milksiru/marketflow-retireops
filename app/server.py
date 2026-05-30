import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from app import db
from app.notifications import send_notification
from app.reports import build_report, market_snapshot


class Handler(BaseHTTPRequestHandler):
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
        if path == "/api/notifications":
            return self._json({"logs": db.list_logs()})
        if path == "/api/notifications/channels":
            return self._json({"channels": db.list_channels()})
        if path.startswith("/api/reports/"):
            return self._json(build_report(path.rsplit("/", 1)[-1]))
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        payload = self._read_json()
        if path == "/api/notifications/test":
            channel = payload.get("channel", "sms")
            recipient = payload.get("recipient", "test-recipient")
            return self._json(send_notification(channel, recipient, "morning"))
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
    body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; }
    main { max-width: 1120px; margin: 0 auto; padding: 28px; }
    h1 { margin: 0 0 8px; font-size: 34px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-top: 18px; }
    .card { background: #111c33; border: 1px solid #26344f; border-radius: 8px; padding: 16px; }
    .badge { display: inline-block; padding: 4px 9px; border-radius: 999px; background: #155e75; margin: 4px 4px 0 0; }
    .muted { color: #a8b3c7; }
    button { background: #38bdf8; border: 0; border-radius: 6px; padding: 9px 12px; cursor: pointer; }
    pre { white-space: pre-wrap; color: #dbeafe; }
  </style>
</head>
<body>
  <main>
    <h1>MarketFlow RetireOps</h1>
    <p class="muted">시장 흐름, DC 운용 참고, 리포트 알림을 한 곳에서 봅니다.</p>
    <section class="grid">
      <div class="card"><h2>Market Mood</h2><div id="mood"></div></div>
      <div class="card"><h2>Global Index</h2><div id="indices"></div></div>
      <div class="card"><h2>My Watchlist</h2><div id="watchlist"></div></div>
      <div class="card"><h2>DC Retirement</h2><div id="dc"></div></div>
      <div class="card"><h2>Alert Preview</h2><button onclick="sendTest()">Send mock SMS</button><pre id="test"></pre></div>
    </section>
  </main>
  <script>
    async function load() {
      const data = await fetch('/api/dashboard').then(r => r.json());
      document.getElementById('mood').innerHTML = `<strong>${data.mood}</strong><br>` + data.badges.map(b => `<span class="badge">${b}</span>`).join('');
      document.getElementById('indices').innerHTML = data.indices.map(i => `<p>${i.symbol}: ${i.value}</p>`).join('');
      document.getElementById('watchlist').innerHTML = data.watchlist.map(i => `<p>${i.symbol}: ${i.signal}</p>`).join('');
      document.getElementById('dc').innerHTML = `<p>${data.dc.style}</p><p>${data.dc.rebalance}</p><p class="muted">${data.dc.plain_language}</p>`;
    }
    async function sendTest() {
      const res = await fetch('/api/notifications/test', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({channel:'sms', recipient:'010-0000-0000'})}).then(r => r.json());
      document.getElementById('test').textContent = JSON.stringify(res, null, 2);
    }
    load();
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
