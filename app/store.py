"""Permanent storage layout.

  data/raw/<category>/     original files exactly as received (PDF, DOCX, HTML ...)  -> KEEP
  data/corpus/<category>/  cleaned text + metadata, one .md per source             -> KEEP (source of truth)
  data/inbox/              drop zone for new files; processed files move to raw/    -> transient
  data/knowledge.db        search index, rebuilt from corpus/ at any time            -> local only
  qa_log (in the db)       user questions, purged after LOG_DAYS                     -> local only

The database is never the only copy of any content.
"""
import hashlib
import re
import shutil
import time
from pathlib import Path

from . import importer, knowledge

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data"
LOG_DAYS = 30
META_KEYS = ("title", "category", "source_url", "publisher", "source_type",
             "effective_date", "retrieved_at")


def slug(text, limit=60):
    s = re.sub(r'[\\/:*?"<>|\s]+', "-", text or "").strip("-.")
    return s[:limit] or "untitled"


def _cat_dir(data_dir, kind, category):
    p = Path(data_dir) / kind / (slug(category) if category else "_uncategorised")
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_raw(data_dir, category, name, data):
    """Keep the original bytes. Identical content is stored once. Returns the path."""
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    h = hashlib.sha1(data).hexdigest()[:8]
    p = _cat_dir(data_dir, "raw", category) / f"{slug(stem)}-{h}{ext}"
    if not p.exists():
        p.write_bytes(data)
    return p


def _one_line(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def save_corpus(data_dir, meta, text):
    """One cleaned .md per source. Same URL (or same title) overwrites, so the corpus
    always holds the latest cleaned version and never accumulates stale copies."""
    key = meta.get("source_url") or meta.get("title") or text[:80]
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    p = _cat_dir(data_dir, "corpus", meta.get("category", "")) / f"{slug(meta.get('title', ''))}-{h}.md"
    head = "\n".join(f"{k}: {_one_line(meta.get(k))}" for k in META_KEYS)
    p.write_text(f"---\n{head}\n---\n\n{text.strip()}\n", encoding="utf-8")
    return p


def persist(data_dir, meta, text, raw=None):
    """Write the permanent copies. `raw` is (filename, bytes) when there is an original file."""
    meta = dict(meta)
    meta.setdefault("retrieved_at", "") 
    meta["retrieved_at"] = meta["retrieved_at"] or time.strftime("%Y-%m-%d")
    out = {"corpus": str(save_corpus(data_dir, meta, text))}
    if raw:
        out["raw"] = str(save_raw(data_dir, meta.get("category", ""), raw[0], raw[1]))
    return out


# ---- rebuild the index from the permanent copies
def _clear_index(conn):
    conn.execute("DELETE FROM chunks_fts")
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM documents")
    conn.commit()


def rebuild(conn, data_dir):
    """Drop and recreate documents/chunks/FTS from corpus/*.md. qa_log is untouched."""
    _clear_index(conn)
    n = bad = 0
    for f in sorted((Path(data_dir) / "corpus").rglob("*.md")):
        meta, body = importer.parse_front_matter(f.read_text("utf-8"))
        if not body:
            bad += 1
            continue
        knowledge.add_document(
            conn, meta.get("title") or f.stem, body, meta.get("category", ""),
            meta.get("source_url", ""), meta.get("publisher", ""),
            meta.get("source_type", "official"), meta.get("effective_date", ""),
            meta.get("retrieved_at", ""))
        n += 1
    return {"documents": n, "skipped": bad}


# ---- inbox: drop files in, no scraping needed
def parse_inbox_name(name, categories):
    """'Dining__Opening hours.pdf' -> ('Dining', 'Opening hours'). Without the prefix: ('', stem)."""
    stem = Path(name).stem
    if "__" in stem:
        cat, rest = stem.split("__", 1)
        match = next((c for c in categories if c.lower() == cat.strip().lower()), None)
        if match:
            return match, rest.strip() or stem
    return "", stem


def ingest_inbox(conn, data_dir, categories, defaults=None):
    """Process every file in data/inbox/. Successful files move to raw/; failures stay put."""
    inbox = Path(data_dir) / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    report = {"added": [], "duplicate": [], "failed": []}
    for f in sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith(".")):
        try:
            data = f.read_bytes()
            text = importer.bytes_to_text(f.name, data)
            if len(text.strip()) < 20:
                raise importer.ImportFailure("没有提取到文字（可能是扫描版 PDF，需要 OCR 或人工整理）")
            cat, title = parse_inbox_name(f.name, categories)
            fm, body = importer.parse_front_matter(text)
            meta = {**(defaults or {}), **({"category": cat} if cat else {}),
                    **{k: v for k, v in fm.items() if v}}
            meta.setdefault("title", title)
            meta.setdefault("source_type", "official")
            meta.setdefault("category", "")
            _, _, dup = knowledge.add_document(
                conn, meta["title"], body, meta["category"], meta.get("source_url", ""),
                meta.get("publisher", ""), meta["source_type"], meta.get("effective_date", ""),
                meta.get("retrieved_at", ""))
            persist(data_dir, meta, body, raw=(f.name, data))  # raw/ gets the one permanent copy
            f.unlink()  # inbox is only a drop zone
            report["duplicate" if dup else "added"].append(f.name)
        except Exception as e:  # keep going; the file stays in inbox for the user to fix
            report["failed"].append({"file": f.name, "reason": str(e)})
    return report


# ---- one-off migration: documents that only exist in the db -> corpus/
def _join_chunks(chunks):
    """Undo split_text's overlap: each chunk after the first starts with the last
    CHUNK_OVERLAP characters of the previous one."""
    out, prev = [], ""
    for c in chunks:
        tail = prev[-knowledge.CHUNK_OVERLAP:]
        if out and tail and c.startswith(tail):
            c = c[len(tail):].lstrip("\n")
        out.append(c)
        prev = chunks[len(out) - 1]
    return "\n\n".join(x for x in out if x.strip())


def export_db_to_corpus(conn, data_dir):
    """Write every document in the db to corpus/. Same source_url keeps only the newest row,
    so old copies with navigation noise do not overwrite the clean re-fetch."""
    rows = conn.execute("SELECT * FROM documents ORDER BY id").fetchall()
    newest = {}
    for r in rows:
        newest[r["source_url"] or f"id:{r['id']}"] = r  # later id wins
    for r in newest.values():
        chunks = [c["text"] for c in conn.execute(
            "SELECT text FROM chunks WHERE doc_id=? ORDER BY idx", (r["id"],))]
        save_corpus(data_dir, {k: r[k] for k in META_KEYS}, _join_chunks(chunks))
    return {"exported": len(newest), "skipped_older_duplicates": len(rows) - len(newest)}


# ---- OCR for image-only PDFs (Apple Vision via tools/ocr_pdf.swift, offline)
OCR_TOOL = Path(__file__).resolve().parent.parent / "tools" / "ocr_pdf.swift"


def ocr_pdf(pdf_path, first=None, last=None, timeout=3600):
    """Returns OCR text. Raises ImportFailure if swift/Vision is unavailable or OCR fails."""
    import subprocess
    import tempfile
    if not shutil.which("swift"):
        raise importer.ImportFailure("没有找到 swift（仅 macOS 自带），无法本地 OCR")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "o.txt"
        cmd = ["swift", str(OCR_TOOL), str(pdf_path), str(out)] + ([str(first), str(last)] if first else [])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 or not out.exists():
            raise importer.ImportFailure(f"OCR 失败: {r.stderr[-300:]}")
        return out.read_text("utf-8")


_OCR_NOTE = "（本文由扫描页面 OCR 识别，个别字词可能有误，关键信息请以官方原文为准。）"


def ingest_ocr(conn, data_dir, pdf_path, meta, first=None, last=None):
    """OCR a PDF, then index + persist like any other document. raw/ keeps the original PDF."""
    pdf_path = Path(pdf_path)
    text = ocr_pdf(pdf_path, first, last).strip()
    if len(text) < 200:
        raise importer.ImportFailure("OCR 后仍几乎没有文字")
    meta = dict(meta)
    meta.setdefault("title", pdf_path.stem)
    meta["retrieved_at"] = meta.get("retrieved_at") or time.strftime("%Y-%m-%d")
    body = f"{_OCR_NOTE}\n\n{text}"
    _, _, dup = knowledge.add_document(
        conn, meta["title"], body, meta.get("category", ""), meta.get("source_url", ""),
        meta.get("publisher", ""), meta.get("source_type", "student"),
        meta.get("effective_date", ""), meta["retrieved_at"])
    persist(data_dir, meta, body, raw=(pdf_path.name, pdf_path.read_bytes()))
    return {"chars": len(text), "duplicate": dup}


# ---- local-only data hygiene
def purge_log(conn, days=LOG_DAYS):
    if days is None or days <= 0:
        return 0
    try:
        cur = conn.execute("DELETE FROM qa_log WHERE ts < ?", (time.time() - days * 86400,))
    except Exception:  # table not created yet
        return 0
    conn.commit()
    return cur.rowcount
