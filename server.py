"""HKUST Freshmen Assistant - demo server (standard library only; pypdf optional for PDFs).

Run:  python3 server.py   ->  http://127.0.0.1:8000
The API key is only used per request in memory; it is never stored or logged.
"""
import json
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app import agent, importer, knowledge, rag, refresh, store

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_UPLOAD = 40 * 1024 * 1024
_lock = threading.Lock()  # SQLite writes are serialised
DB = {"path": None, "data": None}  # data = folder holding raw/ corpus/ inbox/
BUILD = time.strftime("%H:%M:%S")  # server start time, shown in the UI to tell old/new processes apart

SOURCES = json.loads((ROOT / "data" / "sources.json").read_text("utf-8"))
CATEGORIES = ["Hall", "Dining", "Printing", "WiFi", "Sports", "General", "Map", "Events"]

# ---- public demo mode (off by default; the local app is unchanged) ---------------------------
# Turned on with FRESHMEN_PUBLIC=1. Then: only /api/chat is open, the model key / model / base URL
# come from the SERVER (env), never from the browser, and chats are rate-limited.
#   FRESHMEN_API_KEY, FRESHMEN_MODEL, FRESHMEN_BASE_URL   server-side model settings
#   FRESHMEN_PER_IP (default 20) per FRESHMEN_WINDOW seconds (default 600); FRESHMEN_DAILY (default 300) in total
#   FRESHMEN_TRUST_PROXY=1  take the client IP from X-Forwarded-For (only behind a proxy you control)
PUBLIC = {"on": False, "per_ip": 20, "window": 600, "daily": 300}
_rl_lock = threading.Lock()
_hits = {}                      # ip -> recent chat timestamps
_day = {"d": "", "n": 0}        # chats served today


def public_config(env=None):
    env = os.environ if env is None else env
    if str(env.get("FRESHMEN_PUBLIC", "")).lower() not in ("1", "true", "yes", "on"):
        return {"on": False}

    def num(k, d):
        try:
            return max(1, int(env.get(k, d)))
        except ValueError:
            return d
    return {"on": True, "key": env.get("FRESHMEN_API_KEY", "").strip(), "model": env.get("FRESHMEN_MODEL", "").strip(),
            "base_url": env.get("FRESHMEN_BASE_URL", "").strip() or None, "per_ip": num("FRESHMEN_PER_IP", 20),
            "window": num("FRESHMEN_WINDOW", 600), "daily": num("FRESHMEN_DAILY", 300),
            "trust_proxy": str(env.get("FRESHMEN_TRUST_PROXY", "")).lower() in ("1", "true", "yes", "on")}


def rate_limit(ip, now=None):
    """None if allowed, else 'ip' / 'daily'. Counts the chat when allowed."""
    now = time.time() if now is None else now
    with _rl_lock:
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        if _day["d"] != today:
            _day.update(d=today, n=0)
        if _day["n"] >= PUBLIC["daily"]:
            return "daily"
        recent = [t for t in _hits.get(ip, []) if now - t < PUBLIC["window"]]
        if len(recent) >= PUBLIC["per_ip"]:
            _hits[ip] = recent
            return "ip"
        recent.append(now)
        _hits[ip] = recent
        _day["n"] += 1
        if len(_hits) > 5000:  # forget stale clients
            for k in [k for k, v in _hits.items() if not v or now - v[-1] >= PUBLIC["window"]]:
                del _hits[k]
    return None


def db():
    conn = knowledge.connect(DB["path"])
    conn.execute("CREATE TABLE IF NOT EXISTS qa_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, "
                 "question TEXT, mode TEXT, flags TEXT, answer TEXT, sources TEXT, model TEXT, ms INTEGER)")
    return conn


def add_text(conn, title, text, meta, raw=None):
    """Index the text AND write the permanent copies (corpus/*.md, plus raw/ if an original exists)."""
    fm, body = importer.parse_front_matter(text)
    m = {**meta, **{k: v for k, v in fm.items() if v}}
    m["title"] = m.get("title") or title
    m.setdefault("source_type", "official")
    with _lock:
        res = knowledge.add_document(
            conn, m["title"], body, m.get("category", ""), m.get("source_url", ""),
            m.get("publisher", ""), m["source_type"],
            m.get("effective_date", ""), m.get("retrieved_at", ""))
        store.persist(DB["data"] or store.DEFAULT_DATA, m, body, raw=raw)
    return res


class Handler(BaseHTTPRequestHandler):
    server_version = "FreshmenDemo/1.0"

    def log_message(self, fmt, *args):  # no request-line logging (could contain query text)
        pass

    # ---- helpers
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self, limit=MAX_UPLOAD):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("文件过大")
        return self.rfile.read(n)

    def read_json(self):
        return json.loads(self.read_body(2_000_000) or b"{}")

    def client_ip(self):
        if PUBLIC.get("trust_proxy"):
            fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if fwd:
                return fwd[:64]
        return self.client_address[0]

    # ---- routes
    PUBLIC_GET = ("/api/version", "/api/sources", "/api/config", "/api/docs", "/api/refresh")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        if PUBLIC["on"] and path.startswith("/api/") and path not in self.PUBLIC_GET:
            return self.send_json({"error": "public demo: disabled"}, 403)  # no log / search / debug
        if path == "/api/config":
            return self.send_json({"public": PUBLIC["on"], "model": PUBLIC.get("model", ""),
                                   "has_key": bool(PUBLIC.get("key")), "per_ip": PUBLIC.get("per_ip"),
                                   "window": PUBLIC.get("window")})
        if path == "/api/version":
            return self.send_json({"build": BUILD})
        if path == "/api/refresh":  # what the last automatic fetch did (labels + status only)
            return self.send_json(refresh.summary())
        if path == "/api/docs":
            c = db()
            docs = knowledge.list_documents(c)
            if PUBLIC["on"]:  # read-only listing, no internal ids needed to delete anything
                docs = [{k: v for k, v in d.items() if k != "id"} | {"id": 0} for d in docs]
            return self.send_json({"docs": docs, "stats": knowledge.stats(c)})
        if path == "/api/sources":
            return self.send_json({"sources": SOURCES, "categories": CATEGORIES})
        if path == "/api/log":
            rows = db().execute("SELECT * FROM qa_log ORDER BY id DESC LIMIT 200").fetchall()
            return self.send_json({"log": [dict(r) for r in rows]})
        if path == "/api/search":  # debug retrieval without a model
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0]
            return self.send_json({"hits": knowledge.search(db(), q, 8)})
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (STATIC / rel).resolve()
        if STATIC.resolve() not in f.parents and f != STATIC.resolve() or not f.is_file():
            return self.send_json({"error": "not found"}, 404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(f.name)[0] or "text/plain") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_DELETE(self):
        if PUBLIC["on"]:
            return self.send_json({"error": "public demo: read-only"}, 403)
        if self.path.startswith("/api/docs/"):
            try:
                doc_id = int(self.path.rsplit("/", 1)[1])
            except ValueError:
                return self.send_json({"error": "bad id"}, 400)
            with _lock:
                knowledge.delete_document(db(), doc_id)
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            u = urllib.parse.urlparse(self.path)
            qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            route = u.path
            if PUBLIC["on"] and route != "/api/chat":  # upload / import / rebuild / test_connection: closed
                return self.send_json({"error": "public demo: read-only"}, 403)
            if route == "/api/upload":
                return self.upload(qs)
            data = self.read_json()
            if route == "/api/text":
                return self.import_text(data)
            if route == "/api/url":
                return self.import_url(data)
            if route == "/api/inbox":
                with _lock:
                    rep = store.ingest_inbox(db(), DB["data"] or store.DEFAULT_DATA, CATEGORIES)
                return self.send_json(rep)
            if route == "/api/rebuild":
                with _lock:
                    rep = store.rebuild(db(), DB["data"] or store.DEFAULT_DATA)
                return self.send_json(rep)
            if route == "/api/links":
                return self.send_json({"urls": importer.extract_urls(data.get("text", ""))})
            if route == "/api/chat":
                return self.chat(data)
            if route == "/api/test_connection":
                return self.test_connection(data)
            self.send_json({"error": "not found"}, 404)
        except importer.ImportFailure as e:
            self.send_json({"error": str(e), "manual": True}, 422)
        except ValueError as e:
            self.send_json({"error": str(e)}, 400)
        except RuntimeError as e:
            self.send_json({"error": str(e)}, 502)
        except Exception as e:  # pragma: no cover
            self.send_json({"error": f"服务器错误: {type(e).__name__}: {e}"}, 500)

    def upload(self, qs):
        name = urllib.parse.unquote(self.headers.get("X-Filename", "upload.txt"))
        data = self.read_body()
        text = importer.bytes_to_text(name, data)
        if len(text.strip()) < 20:
            raise importer.ImportFailure("没有从文件中提取到文字（可能是扫描版 PDF）")
        meta = {k: qs.get(k, "") for k in ("category", "source_url", "publisher", "source_type",
                                            "effective_date") if qs.get(k)}
        title = Path(name).stem
        doc_id, n, dup = add_text(db(), title, text, meta, raw=(name, data))
        self.send_json({"doc_id": doc_id, "chunks": n, "duplicate": dup, "title": title})

    def import_text(self, d):
        if not d.get("text", "").strip():
            raise ValueError("正文不能为空")
        meta = {k: d.get(k, "") for k in ("category", "source_url", "publisher", "source_type",
                                           "effective_date") if d.get(k)}
        doc_id, n, dup = add_text(db(), d.get("title") or "未命名资料", d["text"], meta)
        self.send_json({"doc_id": doc_id, "chunks": n, "duplicate": dup})

    def import_url(self, d):
        url = (d.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("请输入 http(s) 链接")
        title, text, _ = importer.fetch_url(url)
        meta = {k: d.get(k, "") for k in ("category", "publisher", "source_type", "effective_date") if d.get(k)}
        meta["source_url"] = url
        doc_id, n, dup = add_text(db(), d.get("title") or title, text, meta)
        self.send_json({"doc_id": doc_id, "chunks": n, "duplicate": dup, "title": title, "chars": len(text)})

    def chat(self, d):
        q = (d.get("question") or "").strip()
        if not q:
            raise ValueError("问题不能为空")
        if len(q) > 2000:
            raise ValueError("问题过长")
        conn = db()
        t0 = time.time()
        cat = d.get("category") or None
        key = (d.get("api_key") or "").strip()
        model = d.get("model") or "gpt-4o-mini"
        base_url = d.get("base_url")
        history = d.get("history")
        if PUBLIC["on"]:
            # the browser cannot choose the key, model or endpoint; history is trimmed; chats are rate-limited
            key, model, base_url = PUBLIC["key"], PUBLIC["model"] or model, PUBLIC["base_url"]
            d["model"] = model
            history = history[-8:] if isinstance(history, list) else None
            if cat not in CATEGORIES:
                cat = None
            why = rate_limit(self.client_ip())
            if why:
                return self.send_json({"error": "使用次数已达上限，请稍后再试 / Rate limit reached, please try again later."
                                       if why == "ip" else
                                       "今天的演示额度已用完，请明天再试 / Today's demo quota is used up, please try tomorrow."}, 429)
        if d.get("agent", True) or PUBLIC["on"]:
            res = agent.run(lambda qq, k, c=None: knowledge.search(conn, qq, k, c), q, key, model,
                            base_url, history, CATEGORIES, cat)
        else:  # plain retrieval + answer (kept for comparison / debugging)
            res = rag.answer(lambda qq, k: knowledge.search(conn, qq, k, cat), q, key, model,
                             base_url, history)
            res["trace"] = None
        ms = int((time.time() - t0) * 1000)
        # The question log stays on the server only (30-day purge). It is not exposed in public mode,
        # and it never contains the API key. Reviewers' questions are real user data: do not share the .db.
        conn.execute("INSERT INTO qa_log(ts,question,mode,flags,answer,sources,model,ms) VALUES(?,?,?,?,?,?,?,?)",
                     (time.time(), q, res["mode"], ",".join(res["flags"]), res["answer"],
                      json.dumps([s["url"] for s in res["sources"]]), d.get("model", ""), ms))
        conn.commit()
        res["ms"] = ms
        self.send_json(res)

    def test_connection(self, d):
        key = (d.get("api_key") or "").strip()
        if not key:
            raise ValueError("请先填写 API Key")
        out = rag.call_llm(key, d.get("model") or "gpt-4o-mini",
                           [{"role": "user", "content": "Reply with: OK"}], d.get("base_url"), timeout=30)
        self.send_json({"ok": True, "reply": out[:60]})


def make_server(host="127.0.0.1", port=8000, db_path=None, public=None):
    """public=None reads FRESHMEN_PUBLIC* from the environment; tests can pass a dict from public_config()."""
    PUBLIC.clear()
    PUBLIC.update({"on": False, "per_ip": 20, "window": 600, "daily": 300})
    PUBLIC.update(public_config() if public is None else public)
    _hits.clear()
    _day.update(d="", n=0)
    DB["path"] = db_path
    DB["data"] = Path(db_path).parent if db_path else store.DEFAULT_DATA
    c = db()
    store.purge_log(c)  # questions are kept for store.LOG_DAYS only
    c.close()
    return ThreadingHTTPServer((host, port), Handler)


def load_env(path=None):
    """Read KEY=VALUE lines from .env (git-ignored, never packaged) into os.environ without overriding real env vars."""
    p = Path(path) if path else ROOT / ".env"
    if not p.is_file():
        return []
    loaded = []
    for line in p.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            loaded.append(k)
    return loaded


def startup_tasks(public_on):
    """On boot: build the index from data/corpus if it is empty, then keep the pages fresh in the background.
    FRESHMEN_REFRESH_HOURS: hours between automatic fetches (default 24 in public mode, 0 = off; set it locally to opt in)."""
    c = db()
    if knowledge.stats(c)["documents"] == 0:
        print("index empty -> rebuilding from data/corpus:", store.rebuild(c, DB["data"] or store.DEFAULT_DATA), flush=True)
    c.close()
    try:
        hours = float(os.environ.get("FRESHMEN_REFRESH_HOURS", "24" if public_on else "0"))
    except ValueError:
        hours = 0
    if hours > 0:
        threading.Thread(target=refresh.loop, name="refresh", daemon=True, args=(hours, db, DB["data"] or store.DEFAULT_DATA, SOURCES),
                         kwargs={"lock": _lock}).start()
        print(f"auto-fetch: official pages now, then every {hours:g} h", flush=True)
    return hours


if __name__ == "__main__":
    # Local use: python3 server.py [port]  (127.0.0.1 only).
    # Public demo: put FRESHMEN_PUBLIC=1 and FRESHMEN_API_KEY=... in .env (or real env vars) and run python3 server.py
    # (PORT env var is honoured so hosting platforms can set it; it listens on 0.0.0.0 only in public mode.)
    load_env()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8000))
    cfg = public_config()
    host = "0.0.0.0" if cfg["on"] else "127.0.0.1"
    srv = make_server(host=host, port=port, public=cfg)
    startup_tasks(cfg["on"])
    if cfg["on"]:
        print(f"PUBLIC DEMO MODE on {host}:{port} | key {'set' if cfg['key'] else 'MISSING'} | model {cfg['model'] or '(client)'} | "
              f"{cfg['per_ip']}/{cfg['window']}s per IP, {cfg['daily']}/day", flush=True)
    else:
        print(f"HKUST Freshmen Assistant demo: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
