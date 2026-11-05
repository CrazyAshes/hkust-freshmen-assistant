"""Data management without the browser.

  python3 manage.py inbox                      process every file in data/inbox/ (no scraping)
  python3 manage.py rebuild                    rebuild the search index from data/corpus/
  python3 manage.py status                     what is stored where
  python3 manage.py ocr FILE.pdf --category General --title "..." [--source-url URL]
         [--publisher X] [--source-type student|official] [--pages 3-10]
                                               OCR an image-only PDF (macOS, offline) and ingest it
"""
import argparse
import sys
from pathlib import Path

from app import importer, knowledge, store

CATEGORIES = ["Hall", "Dining", "Printing", "WiFi", "Sports", "General", "Map", "Events"]


def cmd_ocr(conn, D, argv):
    ap = argparse.ArgumentParser(prog="manage.py ocr")
    ap.add_argument("file")
    ap.add_argument("--category", required=True, choices=CATEGORIES)
    ap.add_argument("--title", default="")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--publisher", default="")
    ap.add_argument("--source-type", default="student", choices=["official", "student"])
    ap.add_argument("--effective-date", default="")
    ap.add_argument("--pages", default="", help="e.g. 3-10 (default: all)")
    a = ap.parse_args(argv)
    first = last = None
    if a.pages:
        first, last = (int(x) for x in a.pages.split("-"))
    meta = {"title": a.title or Path(a.file).stem, "category": a.category, "source_url": a.source_url,
            "publisher": a.publisher, "source_type": a.source_type, "effective_date": a.effective_date}
    try:
        print(store.ingest_ocr(conn, D, a.file, meta, first, last))
    except importer.ImportFailure as e:
        print("FAILED:", e)
        return 1
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    D = store.DEFAULT_DATA
    conn = knowledge.connect()
    if cmd == "inbox":
        r = store.ingest_inbox(conn, D, CATEGORIES)
        print(f"added {len(r['added'])}, duplicate {len(r['duplicate'])}, failed {len(r['failed'])}")
        for f in r["failed"]:
            print(f"  FAILED {f['file']}: {f['reason']}")
    elif cmd == "rebuild":
        print(store.rebuild(conn, D))
    elif cmd == "ocr":
        return cmd_ocr(conn, D, argv[2:])
    elif cmd == "status":
        n = lambda p: sum(1 for x in (D / p).rglob("*") if x.is_file() and not x.name.startswith("."))
        print(f"corpus/ {n('corpus')} files | raw/ {n('raw')} files | inbox/ {n('inbox')} waiting")
        print("index:", knowledge.stats(conn))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
