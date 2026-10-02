"""A tiny stand-in for Slack/email: Alertmanager posts notifications here.

POST /hooks/<channel>   Alertmanager webhook (one URL per receiver/channel)
GET  /                  page listing the notifications, newest first
GET  /api/notifications the same data as JSON
GET  /health            liveness check

Only the standard library is used, so the image stays tiny. If
FORWARD_WEBHOOK_URL is set (a Slack incoming webhook, or a Discord webhook
URL ending in /slack), each notification is also forwarded there.
"""

import html
import json
import os
import re
import threading
import urllib.request
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_NOTIFICATIONS = 200
HOOK_PATH = re.compile(r"^/hooks/([A-Za-z0-9_-]+)$")

_notifications = deque(maxlen=MAX_NOTIFICATIONS)
_lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_notification(channel, payload, received_at=None):
    """Turn Alertmanager's webhook body into a compact record."""
    alerts = []
    for alert in payload.get("alerts", []):
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        alerts.append({
            "status": alert.get("status", "unknown"),
            "name": labels.get("alertname", "unknown"),
            "severity": labels.get("severity", "none"),
            "sensor": labels.get("sensor"),
            "summary": annotations.get("summary", ""),
            "description": annotations.get("description", ""),
            "starts_at": alert.get("startsAt"),
            "ends_at": alert.get("endsAt"),
        })
    return {
        "received_at": received_at or now_iso(),
        "channel": channel,
        "status": payload.get("status", "unknown"),
        "receiver": payload.get("receiver", ""),
        "group": payload.get("groupLabels", {}),
        "alerts": alerts,
    }


def format_text(record):
    """One line per alert, used for the container log and for forwarding."""
    lines = []
    for a in record["alerts"]:
        where = f" [{a['sensor']}]" if a["sensor"] else ""
        lines.append(f"[{record['channel']}] {a['status'].upper()} {a['name']}{where} "
                     f"({a['severity']}): {a['summary']}")
    return "\n".join(lines)


def forward(record):
    url = os.environ.get("FORWARD_WEBHOOK_URL")
    if not url:
        return
    body = json.dumps({"text": format_text(record)}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except OSError as exc:
        print(f"forwarding failed: {exc}", flush=True)


def store(record):
    with _lock:
        _notifications.appendleft(record)


def snapshot():
    with _lock:
        return list(_notifications)


def render_page(records):
    firing = sum(1 for r in records for a in r["alerts"] if a["status"] == "firing")
    resolved = sum(1 for r in records for a in r["alerts"] if a["status"] == "resolved")
    rows = []
    for r in records:
        for a in r["alerts"]:
            css = "firing" if a["status"] == "firing" else "resolved"
            sensor = html.escape(a["sensor"] or "-")
            rows.append(
                f'<tr class="{css}"><td>{html.escape(r["received_at"])}</td>'
                f'<td>{html.escape(r["channel"])}</td>'
                f'<td><b>{html.escape(a["status"].upper())}</b></td>'
                f'<td>{html.escape(a["name"])}</td><td>{html.escape(a["severity"])}</td>'
                f'<td>{sensor}</td><td>{html.escape(a["summary"])}</td></tr>'
            )
    table = "\n".join(rows) or '<tr><td colspan="7">No notifications yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>Alert receiver</title>
<style>
 body {{ font-family: "Segoe UI", system-ui, sans-serif; margin: 0; background: #f4f6f8; color: #1d2733; }}
 header {{ background: #0f172a; color: #f8fafc; padding: 16px 24px; }}
 header h1 {{ margin: 0; font-size: 1.3rem; }}
 header p {{ margin: 4px 0 0; color: #94a3b8; font-size: .9rem; }}
 main {{ padding: 16px 24px; }}
 .counts span {{ display: inline-block; margin-right: 10px; padding: 4px 12px; border-radius: 999px;
   font-weight: 600; font-size: .85rem; }}
 .c-firing {{ background: #fee2e2; color: #b91c1c; }}
 .c-resolved {{ background: #dcfce7; color: #15803d; }}
 table {{ width: 100%; border-collapse: collapse; margin-top: 14px; background: #fff; font-size: .9rem; }}
 th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; }}
 th {{ background: #e2e8f0; }}
 tr.firing td:nth-child(3) {{ color: #b91c1c; }}
 tr.resolved td:nth-child(3) {{ color: #15803d; }}
</style></head>
<body>
<header><h1>Alert receiver</h1>
<p>Notifications delivered by Alertmanager (newest first). This page refreshes every 5 seconds.</p></header>
<main>
<div class="counts"><span class="c-firing">{firing} firing</span><span class="c-resolved">{resolved} resolved</span></div>
<table><thead><tr><th>Received (UTC)</th><th>Channel</th><th>Status</th><th>Alert</th>
<th>Severity</th><th>Sensor</th><th>Summary</th></tr></thead>
<tbody>{table}</tbody></table>
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "alert-receiver/1.0"

    def _send(self, status, body, content_type):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, render_page(snapshot()), "text/html; charset=utf-8")
        elif self.path == "/api/notifications":
            self._send(200, json.dumps(snapshot()), "application/json")
        elif self.path == "/health":
            self._send(200, '{"status": "ok"}', "application/json")
        else:
            self._send(404, '{"error": "not found"}', "application/json")

    def do_POST(self):
        match = HOOK_PATH.match(self.path)
        if not match:
            self._send(404, '{"error": "not found"}', "application/json")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._send(400, '{"error": "invalid JSON"}', "application/json")
            return
        record = parse_notification(match.group(1), payload)
        store(record)
        print(format_text(record), flush=True)
        forward(record)
        self._send(200, '{"status": "received"}', "application/json")

    def log_message(self, fmt, *args):
        # The default access log is noisy (Docker's health check hits us every
        # few seconds); the notifications themselves are printed in do_POST.
        pass


def main():
    port = int(os.environ.get("PORT", "5001"))
    print(f"alert-receiver listening on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
