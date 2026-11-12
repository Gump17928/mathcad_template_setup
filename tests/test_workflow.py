"""Tests for the new-project wizard helpers and the path a new user takes: wizard output must build."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tool"))

from build_template import ProjectError, build_project, load_project  # noqa: E402
from new_project import create_project, discipline_entries, folder_name, unique_key  # noqa: E402
from project_io import default_file_name, default_key  # noqa: E402

INFO = {"name": "Plant", "number": "T-1", "revision": "A", "client": "", "author": "", "date": "2026-01-01"}


class NamingTest(unittest.TestCase):
    def test_default_key_and_file_name(self):
        self.assertEqual(default_key("Electrical"), "ELE")
        self.assertEqual(default_key("HVAC & Fire"), "HVA")
        self.assertEqual(default_file_name("HVAC & Fire"), "HVAC  Fire")

    def test_keys_stay_unique(self):
        taken: set[str] = set()
        keys = [unique_key(n, taken) for n in ("Electrical", "Elevators", "Electronics")]
        self.assertEqual(keys, ["ELE", "EL2", "EL3"])

    def test_folder_name_is_filesystem_safe(self):
        self.assertEqual(folder_name("Riverside / Warehouse #2"), "Riverside_Warehouse_2")


class NewProjectBuildsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name) / "T-1"

    def test_freshly_created_project_builds_all_worksheets(self):
        create_project(self.folder, INFO, discipline_entries(["Structural", "Process Plant"]))
        written = {p.name for p in build_project(self.folder)}
        self.assertEqual(written, {"Structural.mcdx", "Process Plant.mcdx", "Master.mcdx"})
        self.assertTrue((self.folder / "output" / "import_report.txt").exists())

    def test_bad_json_gives_a_message_with_the_line(self):
        self.folder.mkdir()
        (self.folder / "project.json").write_text('{"project": {},\n "disciplines": [}', encoding="utf-8")
        with self.assertRaisesRegex(ProjectError, "line 2"):
            load_project(self.folder)

    def test_duplicate_discipline_keys_are_rejected(self):
        self.folder.mkdir()
        config = {"project": INFO, "disciplines": [
            {"name": "A", "key": "X", "csv": "a.csv"}, {"name": "B", "key": "X", "csv": "b.csv"}]}
        (self.folder / "project.json").write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ProjectError, "unique"):
            load_project(self.folder)


if __name__ == "__main__":
    unittest.main()
