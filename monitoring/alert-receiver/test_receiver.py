"""Tests for the alert receiver. Standard library only: python -m unittest -v"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import receiver

SAMPLE = {
    "status": "firing",
    "receiver": "team-chat",
    "groupLabels": {"sensor": "sensor-1"},
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "SensorOverheat", "severity": "warning", "sensor": "sensor-1"},
            "annotations": {"summary": "Lab is overheating (41.2 °C)"},
            "startsAt": "2026-10-02T10:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
        }
    ],
}


class ParseTests(unittest.TestCase):
    def test_parse_notification(self):
        record = receiver.parse_notification("team-chat", SAMPLE, received_at="t0")
        self.assertEqual(record["channel"], "team-chat")
        self.assertEqual(record["status"], "firing")
        self.assertEqual(record["alerts"][0]["name"], "SensorOverheat")
        self.assertEqual(record["alerts"][0]["sensor"], "sensor-1")

    def test_format_text(self):
        record = receiver.parse_notification("team-chat", SAMPLE)
        self.assertEqual(
            receiver.format_text(record),
            "[team-chat] FIRING SensorOverheat [sensor-1] (warning): Lab is overheating (41.2 °C)",
        )

    def test_page_escapes_html(self):
        payload = {"alerts": [{"status": "firing", "labels": {"alertname": "<script>"}}]}
        page = receiver.render_page([receiver.parse_notification("x", payload)])
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), receiver.Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_webhook_is_stored_and_listed(self):
        req = urllib.request.Request(
            f"{self.base}/hooks/on-call-pager",
            data=json.dumps(SAMPLE).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
        with urllib.request.urlopen(f"{self.base}/api/notifications") as resp:
            records = json.load(resp)
        self.assertEqual(records[0]["channel"], "on-call-pager")

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"{self.base}/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
