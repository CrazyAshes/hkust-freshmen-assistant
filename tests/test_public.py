"""Public demo mode tests. The model is a local MOCK HTTP server (no real LLM, no real key)."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
from app import knowledge  # noqa: E402

SERVER_KEY = "server-secret-key-123"


class Recorder(BaseHTTPRequestHandler):
    seen = []  # (path, authorization header, model)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n))
        Recorder.seen.append((self.path, self.headers.get("Authorization"), body.get("model")))
        sys_msg = body["messages"][0]["content"]
        if "planning step" in sys_msg:
            out = json.dumps({"intent": "campus_question", "categories": [], "standalone_question": "wifi",
                              "sub_questions": [], "search_queries": ["eduroam wifi"], "assumption": "", "clarify": ""})
        else:
            out = "Use eduroam [1]."
        data = json.dumps({"choices": [{"message": {"content": out}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def cfg(base, **kw):
    c = {"on": True, "key": SERVER_KEY, "model": "server-model", "base_url": base, "per_ip": 3, "window": 600,
         "daily": 100, "trust_proxy": False}
    c.update(kw)
    return c


class PublicModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock = HTTPServer(("127.0.0.1", 0), Recorder)
        cls.base = f"http://127.0.0.1:{cls.mock.server_address[1]}"
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.mock.shutdown()

    def start(self, **kw):
        self.dir = tempfile.mkdtemp()
        self.srv = server.make_server(port=0, db_path=Path(self.dir) / "p.db", public=cfg(self.base, **kw))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        c = knowledge.connect(Path(self.dir) / "p.db")
        knowledge.add_document(c, "Wi-Fi", "Connect to eduroam using your HKUST email account.", "WiFi",
                               "https://x/wifi", "ITSO")
        c.close()
        Recorder.seen.clear()
        self.addCleanup(self.srv.shutdown)

    def req(self, path, data=None, method=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body,
                                   method=method or ("POST" if body is not None else "GET"),
                                   headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def chat(self, **extra):
        return self.req("/api/chat", {"question": "how do I connect to wifi", **extra})

    # ---- config
    def test_off_by_default_from_environment(self):
        self.assertFalse(server.public_config({})["on"])
        self.assertFalse(server.public_config({"FRESHMEN_PUBLIC": "0"})["on"])
        c = server.public_config({"FRESHMEN_PUBLIC": "1", "FRESHMEN_API_KEY": " k ", "FRESHMEN_PER_IP": "x"})
        self.assertTrue(c["on"])
        self.assertEqual(c["key"], "k")
        self.assertEqual(c["per_ip"], 20)  # bad number -> default

    # ---- the server's key/model/endpoint win over anything the browser sends
    def test_server_side_key_model_and_endpoint_are_used(self):
        self.start()
        s, body = self.chat(api_key="attacker-key", model="expensive-model", base_url="http://evil.invalid/v1")
        self.assertEqual(s, 200)
        self.assertTrue(Recorder.seen)
        for path, auth, model in Recorder.seen:
            self.assertEqual(auth, f"Bearer {SERVER_KEY}")
            self.assertEqual(model, "server-model")
        self.assertEqual(json.loads(body)["mode"], "llm")

    def test_browser_never_receives_the_key(self):
        self.start()
        outputs = [self.chat(api_key="x")[1], self.req("/api/config")[1], self.req("/api/docs")[1],
                   self.req("/api/sources")[1], self.req("/")[1], self.req("/app.js")[1]]
        for o in outputs:
            self.assertNotIn(SERVER_KEY, o)
        s, body = self.req("/api/config")
        self.assertTrue(json.loads(body)["public"])

    # ---- everything that writes or exposes internals is closed
    def test_write_and_debug_routes_are_closed(self):
        self.start()
        for method, path, data in [
            ("POST", "/api/upload", {}), ("POST", "/api/text", {"text": "x" * 50}),
            ("POST", "/api/url", {"url": "https://example.com"}), ("POST", "/api/inbox", {}),
            ("POST", "/api/rebuild", {}), ("POST", "/api/links", {"text": "a"}),
            ("POST", "/api/test_connection", {"api_key": "k"}), ("DELETE", "/api/docs/1", None),
            ("GET", "/api/log", None), ("GET", "/api/search?q=wifi", None)]:
            s, _ = self.req(path, data, method=method)
            self.assertEqual(s, 403, f"{method} {path}")

    def test_documents_cannot_be_deleted(self):
        self.start()
        s, body = self.req("/api/docs")
        self.assertEqual(s, 200)
        self.assertEqual(json.loads(body)["stats"]["documents"], 1)
        self.req("/api/docs/1", method="DELETE")
        self.assertEqual(json.loads(self.req("/api/docs")[1])["stats"]["documents"], 1)

    # ---- rate limits
    def test_per_ip_limit(self):
        self.start(per_ip=3)
        codes = [self.chat()[0] for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        n_calls = len(Recorder.seen)
        self.chat()
        self.assertEqual(len(Recorder.seen), n_calls)  # limited requests cost nothing

    def test_daily_limit(self):
        self.start(per_ip=100, daily=2)
        codes = [self.chat()[0] for _ in range(4)]
        self.assertEqual(codes, [200, 200, 429, 429])

    def test_limiter_unit_window_and_ip_separation(self):
        server.PUBLIC.update(per_ip=2, window=10, daily=100)
        server._hits.clear()
        server._day.update(d="", n=0)
        self.assertIsNone(server.rate_limit("a", now=1000.0))
        self.assertIsNone(server.rate_limit("a", now=1001.0))
        self.assertEqual(server.rate_limit("a", now=1002.0), "ip")
        self.assertIsNone(server.rate_limit("b", now=1002.0))      # other client unaffected
        self.assertIsNone(server.rate_limit("a", now=1011.5))      # window passed

    def test_x_forwarded_for_ignored_unless_trusted(self):
        self.start(per_ip=1, trust_proxy=False)
        self.assertEqual(self.chat(headers=None)[0], 200)
        # spoofing the header must not give a fresh allowance
        s, _ = self.req("/api/chat", {"question": "wifi"}, headers={"X-Forwarded-For": "9.9.9.9"})
        self.assertEqual(s, 429)

    def test_x_forwarded_for_used_when_trusted(self):
        self.start(per_ip=1, trust_proxy=True)
        h1, h2 = {"X-Forwarded-For": "1.1.1.1"}, {"X-Forwarded-For": "2.2.2.2"}
        self.assertEqual(self.req("/api/chat", {"question": "wifi"}, headers=h1)[0], 200)
        self.assertEqual(self.req("/api/chat", {"question": "wifi"}, headers=h2)[0], 200)
        self.assertEqual(self.req("/api/chat", {"question": "wifi"}, headers=h1)[0], 429)

    # ---- input handling
    def test_invalid_category_and_huge_history_are_ignored(self):
        self.start(per_ip=10)
        s, body = self.chat(category="'; DROP TABLE x;--", history=[{"role": "user", "content": "a"}] * 500)
        self.assertEqual(s, 200)

    def test_missing_server_key_degrades_to_retrieval_only(self):
        self.start(key="")
        s, body = self.chat()
        self.assertEqual(s, 200)
        self.assertEqual(json.loads(body)["mode"], "retrieval_only")
        self.assertFalse(Recorder.seen)

    def test_local_mode_unchanged(self):
        d = tempfile.mkdtemp()
        srv = server.make_server(port=0, db_path=Path(d) / "l.db", public={"on": False})
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        r = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/log")
        self.assertEqual(r.status, 200)
        self.assertFalse(json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config").read())["public"])


if __name__ == "__main__":
    unittest.main()
