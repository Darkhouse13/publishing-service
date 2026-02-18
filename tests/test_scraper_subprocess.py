import io
import json
import unittest
from unittest.mock import patch

import scraper_subprocess


class ScraperSubprocessEmitTests(unittest.TestCase):
    def test_emit_serializes_non_ascii_payload_as_valid_json(self) -> None:
        stream = io.StringIO()
        payload = {"ok": True, "data": {"label": "emoji 🌿", "text": "naive café"}}

        with patch("sys.stdout", stream):
            scraper_subprocess._emit(payload)

        output = stream.getvalue()
        self.assertTrue(output)
        self.assertIn("\\u", output)
        self.assertNotIn("🌿", output)
        parsed = json.loads(output)
        self.assertEqual(parsed["data"]["label"], "emoji 🌿")
        self.assertEqual(parsed["data"]["text"], "naive café")


if __name__ == "__main__":
    unittest.main()
