"""Regression tests for the worksheet generator.

Run from the project root:   python -m unittest discover -s tests -v
Refresh the golden snapshot after an *intended* output change:   python tests/test_build.py --update
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tool"))

from build_template import build_project  # noqa: E402
from csv_import import CsvError, load_discipline, normalise_unit  # noqa: E402

GOLDEN = Path(__file__).with_name("golden_example.json")
_RANDOM_ID = re.compile(r"R[0-9a-f]{16}")
_SAVED_DATE = re.compile(r'last-saved-date="[^"]*"')


def normalised_parts(mcdx: Path) -> dict[str, str]:
    """Package parts as text, with the per-build random ids and timestamps blanked out."""
    parts: dict[str, str] = {}
    with zipfile.ZipFile(mcdx) as z:
        for name in z.namelist():
            data = z.read(name)
            if name.endswith(".XamlPackage"):
                data = zipfile.ZipFile(io.BytesIO(data)).read("Xaml/Document.xaml")
            elif name.endswith(".png"):
                continue
            text = data.decode("utf-8-sig")
            text = _RANDOM_ID.sub("RID", text)
            parts[name] = _SAVED_DATE.sub('last-saved-date="DATE"', text)
    return parts


def snapshot(output_dir: Path) -> dict[str, str]:
    """{'Structural.mcdx::mathcad/worksheet.xml': sha256, ...} for every generated worksheet."""
    snap = {}
    for f in sorted(output_dir.glob("*.mcdx")):
        for part, text in sorted(normalised_parts(f).items()):
            snap[f"{f.name}::{part}"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return snap


def build_example(workdir: Path) -> Path:
    project = workdir / "Example"
    shutil.copytree(ROOT / "projects" / "Example", project, ignore=shutil.ignore_patterns("output", "pdf", "_work"))
    build_project(project)
    return project / "output"


class ExampleSnapshotTest(unittest.TestCase):
    def test_example_project_matches_golden_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual = snapshot(build_example(Path(tmp)))
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        changed = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
        self.assertEqual(changed, [], f"{len(changed)} package part(s) differ from the golden snapshot")


class CsvImportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def load(self, text: str, **kw):
        path = self.dir / "calc.csv"
        path.write_text(text, encoding="utf-8")
        return load_discipline(path, "X_", **kw)

    @staticmethod
    def rows(model):
        return {r.name or r.label: r for s in model.sections for r in s.rows}

    def test_equation_using_earlier_rows_becomes_live_formula(self):
        m = self.load("section,label,name,value,unit,equation\nA,a,a,2,m,\nA,b,b,,m,b = a*3\n")
        rows = self.rows(m)
        self.assertEqual(rows["X_a"].kind, "input")
        self.assertEqual((rows["X_b"].kind, rows["X_b"].expr), ("calc", "X_a*3"))

    def test_formula_that_disagrees_with_value_is_kept_fixed_with_warning(self):
        m = self.load("section,label,name,value,equation\nA,a,a,2,\nA,b,b,100,b = a*3\n")
        self.assertEqual(self.rows(m)["X_b"].kind, "static")
        self.assertTrue(any("formula gives" in w for w in m.warnings))

    def test_unknown_variable_in_formula_stays_text(self):
        m = self.load("section,label,name,value,equation\nA,b,b,,b = nothing*3\n")
        self.assertEqual(self.rows(m)["b"].kind, "text")

    def test_name_is_taken_from_label_brackets(self):
        m = self.load("section,label,value\nA,Design current (I_d),5\n")
        self.assertIn("X_I_d", self.rows(m))

    def test_duplicate_name_is_reported(self):
        m = self.load("section,label,name,value\nA,one,x,1\nA,two,x,2\n")
        self.assertTrue(any("more than once" in w for w in m.warnings))

    def test_summary_defaults_to_live_formulas_and_status_rows(self):
        m = self.load("section,label,name,value,equation,status\nA,a,a,2,,\nA,b,b,,b = a*2,PASS\n")
        kinds = [(i.kind, i.label) for i in m.summary]
        self.assertEqual(kinds, [("result", "b"), ("check", "b")])

    def test_explicit_summary_list_is_respected(self):
        m = self.load("section,label,name,value\nA,a,a,2\nA,b,b,3\n", summary_names=["b"])
        self.assertEqual([i.name for i in m.summary], ["X_b"])

    def test_missing_section_names_the_line(self):
        with self.assertRaisesRegex(CsvError, "line 2"):
            self.load("section,label\n,oops\n")

    def test_missing_file_is_a_friendly_error(self):
        with self.assertRaisesRegex(CsvError, "not found"):
            load_discipline(self.dir / "nope.csv", "X_")

    def test_unit_normalisation(self):
        self.assertEqual(normalise_unit("ohm/1000ft"), "ohm/(1000*ft)")
        self.assertEqual(normalise_unit("kN*m"), "kN*m")
        self.assertIsNone(normalise_unit("furlongs"))
        self.assertEqual(normalise_unit(""), "")


if __name__ == "__main__":
    if "--update" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            snap = snapshot(build_example(Path(tmp)))
        GOLDEN.write_text(json.dumps(snap, indent=1, sort_keys=True), encoding="utf-8")
        print(f"wrote {GOLDEN} ({len(snap)} parts)")
    else:
        unittest.main()
