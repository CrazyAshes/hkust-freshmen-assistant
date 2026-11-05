"""Bilingual answer tests. ALL use a scripted MOCK model: they prove the enforcement logic
(prompt rule, one-language detection, translate fallback, failure handling), not translation quality."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import rag  # noqa: E402

EN = "You can connect to eduroam using your HKUST email account and password, see the ITSO page [1]."
ZH = "你可以使用 HKUST 邮箱账号和密码连接 eduroam，详见 ITSO 页面 [1]。"
BOTH = f"**中文**\n{ZH}\n\n**English**\n{EN}"
HIT = {"title": "Wi-Fi", "publisher": "ITSO", "source_type": "official", "effective_date": "",
       "retrieved_at": "2026-11-01", "source_url": "https://x/wifi", "text": "Use eduroam with your HKUST email."}


class Detect(unittest.TestCase):
    def test_one_language_is_not_bilingual(self):
        self.assertFalse(rag.is_bilingual(EN))
        self.assertFalse(rag.is_bilingual(ZH))

    def test_both_is_bilingual(self):
        self.assertTrue(rag.is_bilingual(BOTH))

    def test_urls_and_citations_do_not_count_as_english(self):
        self.assertFalse(rag.is_bilingual(ZH + " https://www.ust.hk/very/long/english/looking/path [1][2]"))

    def test_prompt_demands_both_languages_for_english_and_chinese_users(self):
        self.assertIn("BOTH languages", rag.SYSTEM_PROMPT)
        self.assertNotIn("language of the user's question", rag.SYSTEM_PROMPT)


class Ensure(unittest.TestCase):
    def setUp(self):
        self._orig = rag.call_llm
        self.calls = []

    def tearDown(self):
        rag.call_llm = self._orig

    def mock(self, reply):
        def f(key, model, msgs, base=None, timeout=90):
            self.calls.append(msgs)
            if isinstance(reply, Exception):
                raise reply
            return reply
        rag.call_llm = f

    def test_already_bilingual_costs_no_extra_call(self):
        self.mock("x")
        self.assertEqual(rag.ensure_bilingual(BOTH, "k", "m"), BOTH)
        self.assertEqual(self.calls, [])

    def test_english_only_gets_translated(self):
        self.mock(BOTH)
        self.assertEqual(rag.ensure_bilingual(EN, "k", "m"), BOTH)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1]["content"], EN)  # the answer itself is what gets translated

    def test_chinese_only_gets_translated(self):
        self.mock(BOTH)
        self.assertEqual(rag.ensure_bilingual(ZH, "k", "m"), BOTH)

    def test_translation_failure_keeps_original(self):
        self.mock(RuntimeError("502"))
        self.assertEqual(rag.ensure_bilingual(EN, "k", "m"), EN)

    def test_bad_translation_keeps_original(self):
        self.mock("still English only, nothing in Chinese here at all, sorry about that")
        self.assertEqual(rag.ensure_bilingual(EN, "k", "m"), EN)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self._orig = rag.call_llm

    def tearDown(self):
        rag.call_llm = self._orig

    def run_q(self, question, model_replies):
        replies = list(model_replies)
        rag.call_llm = lambda *a, **k: replies.pop(0)
        return rag.answer(lambda q, k: [HIT], question, "k", "m")

    def test_english_question_with_english_reply_ends_up_bilingual(self):
        r = self.run_q("How do I connect to Wi-Fi?", [EN, BOTH])
        self.assertTrue(rag.is_bilingual(r["answer"]))

    def test_chinese_question_with_chinese_reply_ends_up_bilingual(self):
        r = self.run_q("怎么连接 Wi-Fi？", [ZH, BOTH])
        self.assertTrue(rag.is_bilingual(r["answer"]))

    def test_fixed_replies_are_bilingual(self):
        for t in (rag.GREETING_ANSWER, rag.NO_SOURCE_ANSWER, rag.OUT_OF_SCOPE_ANSWER, rag.READ_ONLY_ANSWER):
            self.assertTrue(rag.is_bilingual(t), t[:30])
        r = rag.answer(lambda q, k: [HIT], "How do I connect to Wi-Fi?", "", "m")  # no key
        self.assertTrue(rag.is_bilingual(r["answer"]))


if __name__ == "__main__":
    unittest.main()
