import json
import unittest
from os import environ
from unittest.mock import patch

from automating_wf.engine.config import EngineRunOptions


class EngineConfigTests(unittest.TestCase):
    def test_from_env_loads_defaults_and_aliases(self) -> None:
        seed_map = {"THE_SUNDAY_PATIO": ["patio furniture", "small patio ideas"]}
        with patch.dict(
            environ,
            {
                "PINTEREST_SEED_MAP_JSON": json.dumps(seed_map),
                "PINTEREST_TRENDS_REGION": "US",
                "PINTEREST_TRENDS_RANGE": "monthly",
                "PINTEREST_TRENDS_TOP_N": "17",
                "PINTEREST_PINCLICKS_WINNERS_PER_RUN": "6",
                "WP_POST_STATUS": "pending",
            },
            clear=True,
        ):
            opts = EngineRunOptions.from_env("THE_SUNDAY_PATIO")

        self.assertEqual(opts.blog_suffix, "THE_SUNDAY_PATIO")
        self.assertEqual(opts.seed_keywords, ["patio furniture", "small patio ideas"])
        self.assertEqual(opts.trends_region, "US")
        self.assertEqual(opts.trends_range, "monthly")
        self.assertEqual(opts.trends_top_n, 17)
        self.assertEqual(opts.winners_count, 6)
        self.assertEqual(opts.publish_status, "pending")
        self.assertIsNone(opts.csv_first_publish_at)
        self.assertEqual(opts.csv_cadence_minutes, 240)
        self.assertEqual(opts.pinclicks_max_records, 25)
        self.assertFalse(opts.headed)
        self.assertIsNone(opts.resume_run_id)

    def test_from_ui_requires_blog_suffix(self) -> None:
        with self.assertRaises(ValueError):
            EngineRunOptions.from_ui({})

    def test_from_ui_overrides_provided_fields_only(self) -> None:
        seed_map = {"THE_SUNDAY_PATIO": ["seed a", "seed b"]}
        with patch.dict(
            environ,
            {
                "PINTEREST_SEED_MAP_JSON": json.dumps(seed_map),
                "PINTEREST_TRENDS_FILTER_REGION": "GLOBAL",
                "PINTEREST_TRENDS_FILTER_RANGE": "12m",
                "PINTEREST_TRENDS_TOP_KEYWORDS": "20",
                "PINTEREST_PINCLICKS_WINNERS_PER_RUN": "5",
                "WP_POST_STATUS": "draft",
            },
            clear=True,
        ):
            opts = EngineRunOptions.from_ui(
                {
                    "blog_suffix": "THE_SUNDAY_PATIO",
                    "seed_keywords": "edited one\nedited two",
                    "trends_top_n": 9,
                    "winners_count": 3,
                    "publish_status": "publish",
                    "csv_first_publish_at": "2026-03-16 09:30",
                    "csv_cadence_minutes": 180,
                    "headed": True,
                }
            )

        self.assertEqual(opts.blog_suffix, "THE_SUNDAY_PATIO")
        self.assertEqual(opts.seed_keywords, ["edited one", "edited two"])
        self.assertEqual(opts.trends_region, "GLOBAL")
        self.assertEqual(opts.trends_range, "12m")
        self.assertEqual(opts.trends_top_n, 9)
        self.assertEqual(opts.winners_count, 3)
        self.assertEqual(opts.publish_status, "publish")
        self.assertEqual(opts.csv_first_publish_at, "2026-03-16 09:30")
        self.assertEqual(opts.csv_cadence_minutes, 180)
        self.assertTrue(opts.headed)

    def test_from_ui_minimal_payload_matches_from_env_defaults(self) -> None:
        seed_map = {"THE_SUNDAY_PATIO": ["a", "b"]}
        with patch.dict(
            environ,
            {
                "PINTEREST_SEED_MAP_JSON": json.dumps(seed_map),
                "PINTEREST_TRENDS_FILTER_REGION": "GLOBAL",
                "PINTEREST_TRENDS_FILTER_RANGE": "12m",
                "PINTEREST_TRENDS_TOP_KEYWORDS": "20",
                "PINTEREST_PINCLICKS_WINNERS_PER_RUN": "5",
                "WP_POST_STATUS": "draft",
            },
            clear=True,
        ):
            env_opts = EngineRunOptions.from_env("THE_SUNDAY_PATIO")
            ui_opts = EngineRunOptions.from_ui({"blog_suffix": "THE_SUNDAY_PATIO"})

        self.assertEqual(ui_opts, env_opts)


if __name__ == "__main__":
    unittest.main()
