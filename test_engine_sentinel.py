import unittest
from pathlib import Path

from engine_sentinel import SCENARIOS, analyze_engine, load_csv, make_demo, render


class EngineSentinelTests(unittest.TestCase):
    def test_demo_scenarios(self):
        source = Path(__file__).parent / "data" / "test_demo.csv"
        try:
            make_demo(source)
            groups = load_csv(source)
            self.assertEqual(set(groups), set(SCENARIOS))
            results = {engine: analyze_engine(engine, rows) for engine, rows in groups.items()}
            self.assertEqual(results["ENG-102"]["status"], "SERVICE SOON")
            self.assertEqual(results["ENG-103"]["status"], "SERVICE SOON")
            self.assertEqual(results["ENG-104"]["status"], "WATCH")
            self.assertEqual(results["ENG-105"]["status"], "INSUFFICIENT DATA")
            self.assertEqual(results["ENG-106"]["status"], "NORMAL")
            self.assertIn("synthetic demo", render(list(results.values()), source))
        finally:
            source.unlink(missing_ok=True)

    def test_missing_required_column_is_explained(self):
        source = Path(__file__).parent / "data" / "test_bad.csv"
        try:
            source.write_text("engine_id,timestamp_utc\nENG-1,2026-10-26T00:00:00Z\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing columns"):
                load_csv(source)
        finally:
            source.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

