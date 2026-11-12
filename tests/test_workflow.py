"""Tests for the new-project wizard helpers, blank (CSV-less) disciplines, and the path a new user takes."""
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tool"))

from blank_template import find_name_clashes  # noqa: E402
from build_template import build_project  # noqa: E402
from mcdx_results import WorksheetReadError, read_designated_outputs  # noqa: E402
from new_project import create_project, discipline_entries, folder_name, unique_key  # noqa: E402
from project_config import ProjectError, load_project  # noqa: E402
from project_io import default_file_name, default_key  # noqa: E402

INFO = {"name": "Plant", "number": "T-1", "revision": "A", "client": "", "author": "", "date": "2026-01-01"}
EXAMPLE_CALCS = ROOT / "projects" / "Example" / "calcs"


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

    def test_project_without_csv_files_builds_blank_templates(self):
        create_project(self.folder, INFO, discipline_entries(["Structural", "Process Plant"]))
        written = {p.name for p in build_project(self.folder)}
        self.assertEqual(written, {"Structural.mcdx", "Process Plant.mcdx", "Master.mcdx"})
        self.assertFalse((self.folder / "calcs").exists())
        self.assertTrue((self.folder / "output" / "import_report.txt").exists())

    def test_project_with_starter_csv_files_builds(self):
        create_project(self.folder, INFO, discipline_entries(["Structural", "Process Plant"], starter_csv=True))
        written = {p.name for p in build_project(self.folder)}
        self.assertEqual(written, {"Structural.mcdx", "Process Plant.mcdx", "Master.mcdx"})
        self.assertTrue((self.folder / "calcs" / "Structural.csv").exists())

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

    def test_csv_is_optional_for_a_discipline(self):
        self.folder.mkdir()
        config = {"project": INFO, "disciplines": [{"name": "Process"}, {"name": "Civil", "csv": "c.csv"}]}
        (self.folder / "project.json").write_text(json.dumps(config), encoding="utf-8")
        process, civil = load_project(self.folder).disciplines
        self.assertEqual((process.csv, civil.csv), (None, "c.csv"))


class HandWrittenDisciplineTest(unittest.TestCase):
    """A discipline with no CSV: blank template first, then the engineer's own file is kept and read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name) / "T-1"
        (self.folder / "calcs").mkdir(parents=True)
        shutil.copy(EXAMPLE_CALCS / "Structural.csv", self.folder / "calcs" / "Structural.csv")
        config = {"project": INFO, "disciplines": [
            {"name": "Structural", "key": "STR", "csv": "calcs/Structural.csv"}, {"name": "Hand", "key": "HAN"}]}
        (self.folder / "project.json").write_text(json.dumps(config), encoding="utf-8")
        self.output = self.folder / "output"

    def master_text(self) -> str:
        with zipfile.ZipFile(self.output / "Master.mcdx") as z:
            return z.read("mathcad/worksheet.xml").decode("utf-8")

    def test_blank_template_is_created_with_a_tagged_calculation_area(self):
        build_project(self.folder)
        with zipfile.ZipFile(self.output / "Hand.mcdx") as z:
            worksheet = z.read("mathcad/worksheet.xml").decode("utf-8")
        self.assertIn('tag="calc_calculations"', worksheet)
        self.assertIn('tag="summary"', worksheet)

    def test_existing_discipline_file_is_never_overwritten(self):
        build_project(self.folder)
        hand = self.output / "Hand.mcdx"
        hand.write_bytes(b"the engineer's own work")
        build_project(self.folder)
        self.assertEqual(hand.read_bytes(), b"the engineer's own work")
        report = (self.output / "import_report.txt").read_text(encoding="utf-8")
        self.assertIn("not overwritten", report)
        self.assertIn("could not read", report)  # an unreadable file only costs it its summary lines

    def test_master_lists_outputs_designated_in_the_kept_file(self):
        build_project(self.folder)
        shutil.copy(self.output / "Structural.mcdx", self.output / "Hand.mcdx")  # stands in for a hand-written file
        build_project(self.folder)
        self.assertEqual(self.master_text().count("STR_M_Ed"), 2)  # Structural's own summary line and Hand's
        with zipfile.ZipFile(self.output / "Master.mcdx") as z:
            includes = [n for n in z.namelist() if n.startswith("mathcad/include/")]
        self.assertEqual(len(includes), 1)  # only the CSV discipline carries a cached copy

    def test_variable_names_shared_between_disciplines_are_reported(self):
        build_project(self.folder)
        shutil.copy(self.output / "Structural.mcdx", self.output / "Hand.mcdx")
        build_project(self.folder)
        report = (self.output / "import_report.txt").read_text(encoding="utf-8")
        self.assertIn("variable 'STR_M_Ed' is used in more than one discipline", report)


class DesignatedOutputsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        project = Path(self._tmp.name) / "Example"
        shutil.copytree(EXAMPLE_CALCS.parent, project, ignore=shutil.ignore_patterns("output", "pdf", "_work"))
        build_project(project)
        self.output = project / "output"

    def test_outputs_are_read_with_their_variable_and_unit(self):
        by_variable = {o.variable: o for o in read_designated_outputs(self.output / "Structural.mcdx")}
        self.assertEqual(set(by_variable), {"STR_M_Ed", "STR_U"})
        self.assertIn("kN", by_variable["STR_M_Ed"].unit_override_xml)  # shown in kN*m
        self.assertEqual(by_variable["STR_U"].unit_override_xml, "")    # unitless

    def test_inputs_are_not_reported_as_outputs(self):
        names = {o.variable for o in read_designated_outputs(self.output / "Structural.mcdx")}
        self.assertNotIn("STR_w", names)

    def test_an_unreadable_file_raises_a_clear_error(self):
        bad = self.output / "bad.mcdx"
        bad.write_bytes(b"not a zip")
        with self.assertRaisesRegex(WorksheetReadError, "bad.mcdx"):
            read_designated_outputs(bad)


class NameClashTest(unittest.TestCase):
    def test_reports_names_used_by_two_disciplines(self):
        clashes = find_name_clashes({"A": {"x", "y"}, "B": {"y", "z"}})
        self.assertEqual(len(clashes), 1)
        self.assertIn("'y'", clashes[0])
        self.assertIn("A, B", clashes[0])

    def test_no_clash_gives_no_messages(self):
        self.assertEqual(find_name_clashes({"A": {"x"}, "B": {"y"}}), [])


if __name__ == "__main__":
    unittest.main()
