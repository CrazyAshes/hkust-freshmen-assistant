import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import knowledge, store  # noqa: E402

CATS = ["Hall", "Dining", "Printing", "WiFi", "Sports", "General", "Map", "Events"]
BODY = "Opening hours: the gym is open 7am to 11pm on weekdays. " * 12


def fresh():
    d = Path(tempfile.mkdtemp())
    return d, knowledge.connect(d / "k.db")


class StoreTests(unittest.TestCase):
    def test_persist_writes_corpus_and_raw(self):
        d, _ = fresh()
        out = store.persist(d, {"title": "Gym", "category": "Sports", "source_url": "https://x/gym"},
                            BODY, raw=("gym.pdf", b"%PDF-original"))
        self.assertTrue(Path(out["corpus"]).read_text("utf-8").startswith("---\ntitle: Gym"))
        self.assertEqual(Path(out["raw"]).read_bytes(), b"%PDF-original")
        self.assertIn("Sports", out["corpus"])

    def test_same_source_overwrites_corpus(self):
        d, _ = fresh()
        m = {"title": "Gym", "category": "Sports", "source_url": "https://x/gym"}
        store.persist(d, m, "old text " * 40)
        store.persist(d, m, "new text " * 40)
        files = list((d / "corpus").rglob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertIn("new text", files[0].read_text("utf-8"))

    def test_rebuild_restores_search_from_corpus_only(self):
        d, conn = fresh()
        store.persist(d, {"title": "Gym", "category": "Sports", "source_url": "https://x/gym",
                          "effective_date": "2026-09-01"}, BODY)
        r = store.rebuild(conn, d)
        self.assertEqual(r["documents"], 1)
        hits = knowledge.search(conn, "gym opening hours", 3)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["effective_date"], "2026-09-01")
        self.assertEqual(hits[0]["source_url"], "https://x/gym")
        # wipe the db entirely, rebuild again: nothing lost
        d2 = Path(tempfile.mkdtemp())
        c2 = knowledge.connect(d2 / "other.db")
        store.rebuild(c2, d)
        self.assertEqual(knowledge.stats(c2)["documents"], 1)

    def test_rebuild_does_not_duplicate(self):
        d, conn = fresh()
        store.persist(d, {"title": "Gym", "category": "Sports"}, BODY)
        store.rebuild(conn, d)
        store.rebuild(conn, d)
        self.assertEqual(knowledge.stats(conn)["documents"], 1)

    def test_inbox_filename_category_and_move(self):
        d, conn = fresh()
        (d / "inbox").mkdir()
        (d / "inbox" / "Dining__Canteen hours.md").write_text(BODY, "utf-8")
        (d / "inbox" / "random notes.txt").write_text(BODY + " extra", "utf-8")
        r = store.ingest_inbox(conn, d, CATS)
        self.assertEqual(len(r["added"]), 2)
        self.assertFalse(list((d / "inbox").iterdir()))  # moved out
        self.assertEqual(len(list((d / "raw" / "Dining").glob("*.md"))), 1)  # exactly one original kept
        self.assertEqual((d / "raw" / "Dining").glob("*.md").__next__().read_text("utf-8"), BODY)
        docs = {x["title"]: x["category"] for x in knowledge.list_documents(conn)}
        self.assertEqual(docs["Canteen hours"], "Dining")
        self.assertEqual(docs["random notes"], "")
        self.assertTrue(list((d / "corpus" / "Dining").glob("*.md")))

    def test_inbox_front_matter_wins_and_failures_stay(self):
        d, conn = fresh()
        (d / "inbox").mkdir()
        (d / "inbox" / "a.md").write_text(
            "title: Real title\ncategory: Hall\neffective_date: 2026-09-01\n\n" + BODY, "utf-8")
        (d / "inbox" / "bad.xyz").write_bytes(b"???")
        (d / "inbox" / "empty.md").write_text("tiny", "utf-8")
        r = store.ingest_inbox(conn, d, CATS)
        self.assertEqual(r["added"], ["a.md"])
        self.assertEqual({f["file"] for f in r["failed"]}, {"bad.xyz", "empty.md"})
        self.assertEqual({p.name for p in (d / "inbox").iterdir()}, {"bad.xyz", "empty.md"})
        doc = knowledge.list_documents(conn)[0]
        self.assertEqual((doc["title"], doc["category"], doc["effective_date"]),
                         ("Real title", "Hall", "2026-09-01"))

    def test_inbox_duplicate_is_reported(self):
        d, conn = fresh()
        (d / "inbox").mkdir()
        (d / "inbox" / "a.md").write_text(BODY, "utf-8")
        store.ingest_inbox(conn, d, CATS)
        (d / "inbox" / "a.md").write_text(BODY, "utf-8")
        r = store.ingest_inbox(conn, d, CATS)
        self.assertEqual(r["duplicate"], ["a.md"])
        self.assertEqual(knowledge.stats(conn)["documents"], 1)

    def test_export_db_to_corpus_keeps_newest_and_text_roundtrips(self):
        d, conn = fresh()
        long = "\n\n".join(f"Paragraph {i}: " + "word " * 60 for i in range(30))
        knowledge.add_document(conn, "Old", "stale nav text " * 20, "Hall", "https://x/h")
        knowledge.add_document(conn, "New", long, "Hall", "https://x/h")
        r = store.export_db_to_corpus(conn, d)
        self.assertEqual(r["exported"], 1)
        meta_body = (next((d / "corpus").rglob("*.md"))).read_text("utf-8")
        self.assertIn("title: New", meta_body)
        self.assertNotIn("stale nav", meta_body)
        self.assertEqual(meta_body.count("Paragraph 7:"), 1)  # overlap not duplicated

    def test_purge_log(self):
        d, conn = fresh()
        conn.execute("CREATE TABLE qa_log(id INTEGER PRIMARY KEY, ts REAL, question TEXT)")
        now = time.time()
        conn.executemany("INSERT INTO qa_log(ts,question) VALUES(?,?)",
                         [(now - 40 * 86400, "old"), (now - 5 * 86400, "recent")])
        self.assertEqual(store.purge_log(conn, 30), 1)
        self.assertEqual([r[0] for r in conn.execute("SELECT question FROM qa_log")], ["recent"])

    def test_purge_log_without_table_is_safe(self):
        _, conn = fresh()
        self.assertEqual(store.purge_log(conn, 30), 0)

    def test_header_only_pdf_is_rejected_real_pdf_is_not(self):
        root = Path(__file__).resolve().parent.parent.parent
        scan = root / "MSSS舍堂手册.pdf"
        real = root / "UG Resident Handbook 2026-27.pdf"
        if not (scan.exists() and real.exists()):
            self.skipTest("sample PDFs not present")
        from app import importer
        with self.assertRaises(importer.NeedsOCR):
            importer.bytes_to_text(scan.name, scan.read_bytes())
        self.assertGreater(len(importer.bytes_to_text(real.name, real.read_bytes())), 5000)

    def test_noise_filter_unit(self):
        from app import importer
        noise = "2026/11/4, 16:56新手册.pdf\nPage 3 of 85https://docs.qq.com/pdf/XYZ?nlc=1"
        self.assertTrue(all(importer._PAGE_NOISE.search(l) for l in noise.splitlines()))
        self.assertFalse(importer._PAGE_NOISE.search("The gym is open from 7am to 11pm on weekdays."))


if __name__ == "__main__":
    unittest.main()
