"""Auto-refresh the knowledge base from the official public pages.

Read-only towards the world (only GETs public pages) and conservative towards our own data:
- a failed fetch, a manual-export site (WeChat / Tencent Docs / flipbook) or a page that came back
  much shorter than what we already hold NEVER replaces the existing text;
- unchanged pages are left alone; changed pages replace the old copy (index AND data/corpus),
  so nothing stale accumulates.
"""
import hashlib
import re
import threading
import time
from contextlib import nullcontext

from . import importer, knowledge, store

SHRINK_GUARD = 0.5  # new text shorter than this share of the old one = probably a broken page: keep old
STATE = {"running": False, "started": "", "finished": "", "results": []}
_state_lock = threading.Lock()


def is_manual(url):
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    return any(host.endswith(h) for h in importer.MANUAL_HOSTS)


def refresh_source(conn, data_dir, src, fetch=None, lock=None):
    """Returns {label, url, status, note}; status in added|updated|unchanged|kept|manual."""
    fetch = fetch or importer.fetch_url
    lock = lock or nullcontext()
    url = src["url"]
    out = {"label": src.get("label", ""), "url": url, "status": "", "note": ""}
    if is_manual(url):
        out.update(status="manual", note="needs a manual export (put the file in data/inbox/)")
        return out
    try:
        _title, text, _ = fetch(url)
    except Exception as e:  # network, OCR-only PDF, login page ...: keep what we have
        out.update(status="kept", note=str(e)[:160])
        return out
    text = text.strip()
    h = hashlib.sha256((url + "\n" + text).encode("utf-8")).hexdigest()
    with lock:
        rows = conn.execute("SELECT id,title,char_count,content_hash,effective_date FROM documents "
                            "WHERE source_url=?", (url,)).fetchall()
        if any(r["content_hash"] == h for r in rows):
            out.update(status="unchanged")
            return out
        if rows and len(text) < SHRINK_GUARD * max(r["char_count"] for r in rows):
            out.update(status="kept", note=f"new text much shorter ({len(text)} chars), kept the old copy")
            return out
        meta = {"title": rows[0]["title"] if rows else (src.get("label") or _title),
                "category": src.get("category", ""), "source_url": url, "publisher": src.get("publisher", ""),
                "source_type": src.get("source_type", "official"),
                "effective_date": next((r["effective_date"] for r in rows if r["effective_date"]), ""),
                "retrieved_at": time.strftime("%Y-%m-%d")}
        for r in rows:
            knowledge.delete_document(conn, r["id"])
        knowledge.add_document(conn, meta["title"], text, meta["category"], url, meta["publisher"],
                               meta["source_type"], meta["effective_date"], meta["retrieved_at"])
        store.persist(data_dir, meta, text)
    out.update(status="updated" if rows else "added", note=f"{len(text)} chars")
    return out


def refresh_all(db_factory, data_dir, sources, lock=None, fetch=None, pause=0.5):
    with _state_lock:
        if STATE["running"]:
            return STATE
        STATE.update(running=True, started=time.strftime("%Y-%m-%d %H:%M:%S"), finished="", results=[])
    conn = None
    try:
        conn = db_factory()
        for src in sources:
            STATE["results"].append(refresh_source(conn, data_dir, src, fetch, lock))
            if pause and not is_manual(src["url"]):
                time.sleep(pause)
    finally:
        if conn:
            conn.close()
        with _state_lock:
            STATE.update(running=False, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
    return STATE


def loop(hours, *args, **kw):
    """Daemon-thread body: refresh now, then every `hours`. Never raises."""
    while True:
        try:
            refresh_all(*args, **kw)
        except Exception as e:  # pragma: no cover - the server must keep running
            STATE["results"].append({"label": "(refresh loop)", "url": "", "status": "kept", "note": str(e)[:160]})
        time.sleep(max(0.1, hours) * 3600)


def summary():
    r = STATE["results"]
    c = {}
    for x in r:
        c[x["status"]] = c.get(x["status"], 0) + 1
    return {"running": STATE["running"], "started": STATE["started"], "finished": STATE["finished"],
            "counts": c, "results": [{k: x[k] for k in ("label", "status", "note")} for x in r]}
