"""Auto-refresh + .env tests. Fetching is MOCKED (no network); they prove the safety rules, not that the real
HKUST sites are reachable from a server (that must be checked on the deployed machine)."""
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
from app import knowledge, refresh, store  # noqa: E402

URL = "https://itso.hkust.edu.hk/wifi"
SRC = {"category": "WiFi", "label": "Wi-Fi", "url": URL, "publisher": "ITSO", "source_type": "official"}
OLD = "Connect to eduroam using your HKUST email account. " * 12
NEW = "Connect to eduroam with your ITSO username. Updated instructions. " * 12


def fetcher(text=None, exc=None):
    def f(url):
        if exc:
            raise exc
        return "T", text, "text/html"
    return f


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.c = knowledge.connect(self.d / "r.db")
        knowledge.add_document(self.c, "Wi-Fi", OLD, "WiFi", URL, "ITSO", "official", "2026-01-01", "2026-10-01")
        store.persist(self.d, {"title": "Wi-Fi", "category": "WiFi", "source_url": URL, "publisher": "ITSO",
                               "source_type": "official", "effective_date": "2026-01-01"}, OLD)

    def tearDown(self):
        self.c.close()

    def docs(self):
        return self.c.execute("SELECT * FROM documents").fetchall()

    def corpus(self):
        return [f.read_text("utf-8") for f in (self.d / "corpus").rglob("*.md")]

    def test_changed_page_replaces_old_copy_in_index_and_corpus(self):
        r = refresh.refresh_source(self.c, self.d, SRC, fetcher(NEW))
        self.assertEqual(r["status"], "updated")
        self.assertEqual(len(self.docs()), 1)  # replaced, not duplicated
        self.assertIn("ITSO username", knowledge.search(self.c, "ITSO username", 3)[0]["text"])
        self.assertEqual(len(self.corpus()), 1)
        self.assertIn("ITSO username", self.corpus()[0])
        self.assertEqual(self.docs()[0]["effective_date"], "2026-01-01")  # a known effective date is kept

    def test_unchanged_page_is_left_alone(self):
        r = refresh.refresh_source(self.c, self.d, SRC, fetcher(OLD))
        self.assertEqual(r["status"], "unchanged")
        self.assertEqual(self.docs()[0]["retrieved_at"], "2026-10-01")

    def test_failed_fetch_keeps_existing_data(self):
        r = refresh.refresh_source(self.c, self.d, SRC, fetcher(exc=RuntimeError("timeout")))
        self.assertEqual(r["status"], "kept")
        self.assertEqual(len(self.docs()), 1)
        self.assertEqual(self.docs()[0]["char_count"], len(OLD.strip()))

    def test_suspiciously_short_page_does_not_overwrite(self):
        r = refresh.refresh_source(self.c, self.d, SRC, fetcher("Please log in to continue. " * 3))
        self.assertEqual(r["status"], "kept")
        self.assertEqual(self.docs()[0]["char_count"], len(OLD.strip()))
        self.assertIn("eduroam", self.corpus()[0])

    def test_new_source_is_added(self):
        src = {**SRC, "url": "https://itso.hkust.edu.hk/other", "label": "Other"}
        r = refresh.refresh_source(self.c, self.d, src, fetcher(NEW))
        self.assertEqual(r["status"], "added")
        self.assertEqual(len(self.docs()), 2)

    def test_manual_sites_are_never_fetched(self):
        for u in ("https://mp.weixin.qq.com/s/abc", "https://docs.qq.com/pdf/X", "https://ebookshelf.hkust.edu.hk/x"):
            r = refresh.refresh_source(self.c, self.d, {**SRC, "url": u},
                                       lambda url: self.fail("must not fetch " + url))
            self.assertEqual(r["status"], "manual")

    def test_refresh_all_is_single_flight_and_reports(self):
        started = threading.Event()
        release = threading.Event()

        def slow(url):
            started.set()
            release.wait(5)
            return "T", NEW, "text/html"
        t = threading.Thread(target=refresh.refresh_all, args=(lambda: knowledge.connect(self.d / "r.db"), self.d, [SRC]),
                             kwargs={"fetch": slow, "pause": 0})
        t.start()
        self.assertTrue(started.wait(5))
        self.assertTrue(refresh.summary()["running"])
        refresh.refresh_all(lambda: self.fail("second run must not start"), self.d, [SRC], fetch=slow, pause=0)
        release.set()
        t.join(10)
        s = refresh.summary()
        self.assertFalse(s["running"])
        self.assertEqual(s["counts"], {"updated": 1})

    def test_summary_has_no_urls_or_text(self):
        refresh.refresh_all(lambda: knowledge.connect(self.d / "r.db"), self.d, [SRC],
                            fetch=fetcher(exc=RuntimeError("boom")), pause=0)
        for row in refresh.summary()["results"]:
            self.assertEqual(set(row), {"label", "status", "note"})


class EnvAndStartupTests(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_env_file_is_loaded_but_real_env_wins(self):
        p = Path(tempfile.mkdtemp()) / ".env"
        p.write_text('# comment\nFRESHMEN_PUBLIC=1\nFRESHMEN_API_KEY="abc"\nFRESHMEN_MODEL=from-file\nbad line\n', "utf-8")
        os.environ.pop("FRESHMEN_PUBLIC", None)
        os.environ.pop("FRESHMEN_API_KEY", None)
        os.environ["FRESHMEN_MODEL"] = "from-env"
        loaded = server.load_env(p)
        self.assertEqual(sorted(loaded), ["FRESHMEN_API_KEY", "FRESHMEN_PUBLIC"])
        self.assertEqual(os.environ["FRESHMEN_API_KEY"], "abc")
        self.assertEqual(os.environ["FRESHMEN_MODEL"], "from-env")
        self.assertTrue(server.public_config()["on"])

    def test_missing_env_file_is_fine(self):
        self.assertEqual(server.load_env(Path(tempfile.mkdtemp()) / "nope"), [])

    def test_empty_index_is_rebuilt_from_corpus_on_startup(self):
        d = Path(tempfile.mkdtemp())
        store.persist(d, {"title": "Wi-Fi", "category": "WiFi", "source_url": URL, "publisher": "ITSO",
                          "source_type": "official"}, OLD)
        server.make_server(port=0, db_path=d / "s.db", public={"on": False}).server_close()
        os.environ["FRESHMEN_REFRESH_HOURS"] = "0"
        self.assertEqual(server.startup_tasks(False), 0)
        c = knowledge.connect(d / "s.db")
        self.assertEqual(knowledge.stats(c)["documents"], 1)
        c.close()

    def test_refresh_hours_defaults(self):
        d = Path(tempfile.mkdtemp())
        server.make_server(port=0, db_path=d / "s.db", public={"on": False}).server_close()
        os.environ.pop("FRESHMEN_REFRESH_HOURS", None)
        self.assertEqual(server.startup_tasks(False), 0)      # local: off unless asked
        os.environ["FRESHMEN_REFRESH_HOURS"] = "junk"
        self.assertEqual(server.startup_tasks(False), 0)      # bad value -> off


if __name__ == "__main__":
    unittest.main()
