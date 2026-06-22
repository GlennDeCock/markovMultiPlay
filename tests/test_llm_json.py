"""Tests for LLM JSON extraction."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_client import _extract_json, _repair_json_strings


class TestExtractJson(unittest.TestCase):
    def test_plain_object(self):
        out = _extract_json('{"nodes": [{"id": "a", "text": "ok"}]}')
        self.assertEqual(len(out["nodes"]), 1)

    def test_markdown_fence(self):
        raw = '```json\n{"nodes": []}\n```'
        out = _extract_json(raw)
        self.assertEqual(out["nodes"], [])

    def test_unescaped_newlines_in_text(self):
        raw = (
            '{"nodes":[{"id":"x","text":"Line one.\n\nLine two.","exits":[],"items":[]}]}'
        )
        out = _extract_json(raw)
        self.assertIn("Line two", out["nodes"][0]["text"])

    def test_repair_strings(self):
        broken = '{"text":"hello\nworld"}'
        fixed = _repair_json_strings(broken)
        self.assertNotIn("\n", fixed.split('"hello')[1].split('"')[0])
        out = _extract_json(broken)
        self.assertEqual(out["text"], "hello\nworld")


if __name__ == "__main__":
    unittest.main()
