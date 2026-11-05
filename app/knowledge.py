"""Local knowledge base: SQLite + FTS5 (BM25), chunked storage.

Tokenisation: English words (lowercased) plus CJK character bigrams, so that
Chinese and English questions share one index without extra dependencies.
"""
import hashlib
import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge.db"
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "the", "a", "an", "is", "are", "to", "of", "in", "on", "for", "and", "or",
    "do", "does", "how", "what", "where", "when", "can", "i", "my", "me", "it",
    "be", "at", "by", "with", "this", "that", "there", "which", "if", "you",
}


def tokenize(text):
    text = text.lower()
    tokens = [w for w in _WORD.findall(text) if w not in STOPWORDS]
    for run in _CJK.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def connect(path=None):
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            publisher TEXT DEFAULT '',
            source_type TEXT DEFAULT 'official',
            effective_date TEXT DEFAULT '',
            retrieved_at TEXT DEFAULT '',
            content_hash TEXT UNIQUE,
            char_count INTEGER DEFAULT 0,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS chunks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            idx INTEGER NOT NULL,
            text TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            tokens, tokenize='unicode61'
        );
        """
    )
    return conn


def split_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split on paragraph boundaries where possible, with a small overlap."""
    text = text.replace("\r\n", "\n").strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:  # very long paragraph: hard split
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:size])
            p = p[size - overlap:]
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = f"{tail}\n\n{p}" if tail else p
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


def add_document(conn, title, text, category="", source_url="", publisher="",
                 source_type="official", effective_date="", retrieved_at=""):
    """Returns (doc_id, n_chunks, duplicate_flag)."""
    text = text.strip()
    if not text:
        raise ValueError("正文为空，无法入库")
    h = hashlib.sha256((source_url + "\n" + text).encode("utf-8")).hexdigest()
    row = conn.execute("SELECT id FROM documents WHERE content_hash=?", (h,)).fetchone()
    if row:
        return row["id"], 0, True
    retrieved_at = retrieved_at or time.strftime("%Y-%m-%d")
    cur = conn.execute(
        "INSERT INTO documents(title,category,source_url,publisher,source_type,"
        "effective_date,retrieved_at,content_hash,char_count,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (title, category, source_url, publisher, source_type, effective_date,
         retrieved_at, h, len(text), time.time()),
    )
    doc_id = cur.lastrowid
    pieces = split_text(text)
    for i, piece in enumerate(pieces):
        c = conn.execute("INSERT INTO chunks(doc_id,idx,text) VALUES(?,?,?)",
                         (doc_id, i, piece))
        # keep chunk id == fts rowid so we can join cheaply
        conn.execute("INSERT INTO chunks_fts(rowid,tokens) VALUES(?,?)",
                     (c.lastrowid, " ".join(tokenize(title + " " + piece))))
    conn.commit()
    return doc_id, len(pieces), False


def delete_document(conn, doc_id):
    ids = [r["id"] for r in conn.execute("SELECT id FROM chunks WHERE doc_id=?", (doc_id,))]
    conn.executemany("DELETE FROM chunks_fts WHERE rowid=?", [(i,) for i in ids])
    conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()


def list_documents(conn):
    rows = conn.execute(
        "SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.doc_id=d.id) AS n_chunks "
        "FROM documents d ORDER BY d.id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def stats(conn):
    d = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(char_count),0) c FROM documents").fetchone()
    n_chunks = conn.execute("SELECT COUNT(*) n FROM chunks").fetchone()["n"]
    return {"documents": d["n"], "chars": d["c"], "chunks": n_chunks}


def search(conn, query, k=5, category=None):
    """BM25 search. Returns list of dicts with chunk text and source metadata."""
    from .glossary import expand
    toks = list(dict.fromkeys(tokenize(query + " " + expand(query))))[:60]
    if not toks:
        return []
    match = " OR ".join(f'"{t}"' for t in toks)
    sql = (
        "SELECT c.id chunk_id, c.idx, c.text, d.id doc_id, d.title, d.category, "
        "d.source_url, d.publisher, d.source_type, d.effective_date, d.retrieved_at, "
        "bm25(chunks_fts) AS score "
        "FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid "
        "JOIN documents d ON d.id=c.doc_id WHERE chunks_fts MATCH ? "
    )
    args = [match]
    if category:
        sql += "AND d.category=? "
        args.append(category)
    sql += "ORDER BY score LIMIT ?"
    args.append(k)
    return [dict(r) for r in conn.execute(sql, args)]
