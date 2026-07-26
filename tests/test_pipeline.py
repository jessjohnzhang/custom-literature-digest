import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("li", ROOT / "scripts" / "literature_intelligence.py")
li = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(li)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = li.load_config(ROOT / "presets" / "ev-charging.json")
        self.fixture = ROOT / "tests" / "fixtures" / "crossref.json"
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / "state.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_config_is_valid(self):
        self.assertEqual([], li.validate_config(self.config))

    def test_filtering_classification_and_deduplication(self):
        count = li.import_fixture(self.config, self.state, self.fixture)
        self.assertEqual(2, count)
        li.import_fixture(self.config, self.state, self.fixture)
        connection = sqlite3.connect(self.state)
        papers = li.read_papers(connection, "2026-07-01", "2026-07-31")
        connection.close()
        self.assertEqual(2, len(papers))
        titles = {paper["title"] for paper in papers}
        self.assertNotIn("Machine learning for urban bus arrival prediction", titles)
        spatial = next(p for p in papers if p["doi"] == "10.1234/ev.2026.1")
        self.assertIn("EV charging resilience", spatial["topics"])
        self.assertIn(
            "AI, machine learning, optimisation, and spatial analysis applied to EV charging",
            spatial["topics"],
        )

    def test_generate_dashboard_and_reports(self):
        li.import_fixture(self.config, self.state, self.fixture)
        output = Path(self.temp.name) / "output"
        files = li.generate(self.config, self.state, "2026-07-01", "2026-07-31", output)
        self.assertTrue(all(path.exists() for path in files))
        dashboard = files[0].read_text(encoding="utf-8")
        self.assertIn("Applied Energy", dashboard)
        self.assertIn('id="journal"', dashboard)
        self.assertIn("<details><summary>Abstract</summary>", dashboard)
        report = files[1].read_text(encoding="utf-8")
        self.assertIn("Executive summary", report)
        self.assertIn("Emerging trends", report)

    def test_missing_abstract_is_labeled(self):
        paper = {
            "abstract": "",
            "topics": ["Smart charging"],
        }
        self.assertIn("Metadata-only", li.concise_summary(paper))


if __name__ == "__main__":
    unittest.main()
