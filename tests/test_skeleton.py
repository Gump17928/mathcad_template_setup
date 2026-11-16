"""Tests for building against another Mathcad Prime version's skeleton (simulated Prime 10)."""
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tool"))

import prime_skeleton  # noqa: E402
from build_template import build_project  # noqa: E402
from project_config import ProjectError, load_project  # noqa: E402

INFO = {"name": "Plant", "number": "T-1", "revision": "A", "client": "", "author": "", "date": "2026-01-01"}
# Settings a Prime 12 writes that an older Prime does not know.
NEWER_ONLY_SETTINGS = ('bin-oct-hex-mode="false"', 'symbolic-engine="axiom"')


def rewrite_package(src: Path, dest: Path, edit) -> None:
    """Copy a package, letting `edit(name, text)` change the text of each XML part."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            data = zin.read(name)
            if name.endswith((".xml", ".rels")):
                data = edit(name, data.decode("utf-8-sig")).encode("utf-8")
            zout.writestr(name, data)


def pretend_prime10(name: str, text: str) -> str:
    if name == "docProps/app.xml":
        return text.replace("<appVersion>12.0.1.0", "<appVersion>10.0.0.0")
    if name == "mathcad/settings/calculation.xml":
        for setting in NEWER_ONLY_SETTINGS:
            text = text.replace(" " + setting, "")
    if name == "docProps/core.xml":
        text = text.replace("MathCAD Template Generator", "Jane Engineer")
    return text


class SkeletonTestCase(unittest.TestCase):
    """A temporary skeleton folder holding the real Prime 12 skeleton, so tests never touch the repository."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)
        self.skeletons = self.work / "skeleton"
        self.skeletons.mkdir()
        shutil.copy(prime_skeleton.skeleton_path("12"), self.skeletons / "prime12.mcdx")
        original = prime_skeleton.SKELETON_DIR
        prime_skeleton.SKELETON_DIR = self.skeletons
        prime_skeleton.load_skeleton.cache_clear()
        self.addCleanup(self._restore, original)

    @staticmethod
    def _restore(original: Path) -> None:
        prime_skeleton.SKELETON_DIR = original
        prime_skeleton.load_skeleton.cache_clear()

    def project(self, config: dict) -> Path:
        folder = self.work / "T-1"
        (folder / "calcs").mkdir(parents=True)
        shutil.copy(ROOT / "projects" / "Example" / "calcs" / "Structural.csv", folder / "calcs" / "Structural.csv")
        config = {"project": INFO,
                  "disciplines": [{"name": "Structural", "key": "STR", "csv": "calcs/Structural.csv"}], **config}
        (folder / "project.json").write_text(json.dumps(config), encoding="utf-8")
        return folder

    def fake_prime10_sample(self) -> Path:
        folder = self.project({})
        build_project(folder)
        sample = self.work / "sample10.mcdx"
        rewrite_package(folder / "output" / "Structural.mcdx", sample, pretend_prime10)
        return sample


class CaptureTest(SkeletonTestCase):
    def test_captured_skeleton_is_named_by_version_and_made_neutral(self):
        path = prime_skeleton.capture_skeleton(self.fake_prime10_sample())
        self.assertEqual(path.name, "prime10.mcdx")
        self.assertEqual(prime_skeleton.available_versions(), ["12", "10"])
        with zipfile.ZipFile(path) as z:
            self.assertEqual(sorted(z.namelist()), sorted(prime_skeleton.SKELETON_PARTS))
            self.assertNotIn("Jane Engineer", z.read("docProps/core.xml").decode("utf-8"))

    def test_existing_skeleton_is_not_replaced_unless_asked(self):
        sample = self.fake_prime10_sample()
        prime_skeleton.capture_skeleton(sample)
        with self.assertRaisesRegex(prime_skeleton.SkeletonError, "--replace"):
            prime_skeleton.capture_skeleton(sample)
        prime_skeleton.capture_skeleton(sample, replace=True)

    def test_sample_without_header_and_footer_is_explained(self):
        def drop_header(name: str, text: str) -> str:
            if name != "_rels/.rels":
                return text
            return text.replace("header.xml", "x1.xml").replace("footer.xml", "x2.xml")

        sample = self.work / "no_header.mcdx"
        rewrite_package(self.fake_prime10_sample(), sample, drop_header)
        with self.assertRaisesRegex(prime_skeleton.SkeletonError, "header and footer"):
            prime_skeleton.capture_skeleton(sample)

    def test_file_that_is_not_a_worksheet_is_rejected(self):
        bad = self.work / "bad.mcdx"
        bad.write_bytes(b"not a zip")
        with self.assertRaisesRegex(prime_skeleton.SkeletonError, "not a Mathcad worksheet"):
            prime_skeleton.capture_skeleton(bad)

    def test_sample_from_a_different_xml_dialect_is_rejected(self):
        def other_dialect(name: str, text: str) -> str:
            return text.replace("worksheet50", "worksheet60") if name == "mathcad/worksheet.xml" else text

        sample = self.work / "dialect.mcdx"
        rewrite_package(self.fake_prime10_sample(), sample, other_dialect)
        with self.assertRaisesRegex(prime_skeleton.SkeletonError, "namespace"):
            prime_skeleton.capture_skeleton(sample)


class BuildForOlderPrimeTest(SkeletonTestCase):
    def setUp(self):
        super().setUp()
        prime_skeleton.capture_skeleton(self.fake_prime10_sample())
        shutil.rmtree(self.work / "T-1")

    @staticmethod
    def part(mcdx: Path, name: str) -> str:
        with zipfile.ZipFile(mcdx) as z:
            return z.read(name).decode("utf-8")

    def test_prime10_project_is_stamped_and_configured_like_prime10(self):
        folder = self.project({"prime_version": "10"})
        build_project(folder)
        master = folder / "output" / "Master.mcdx"
        self.assertIn("<appVersion>10.0.0.0", self.part(master, "docProps/app.xml"))
        self.assertNotIn("bin-oct-hex-mode", self.part(master, "mathcad/settings/calculation.xml"))

    def test_include_cache_only_uses_settings_the_older_prime_has(self):
        older = self.project({"prime_version": "10"})
        build_project(older)
        cache = next(n for n in zipfile.ZipFile(older / "output" / "Master.mcdx").namelist() if "/include/" in n)
        self.assertNotIn("symbolic-engine", self.part(older / "output" / "Master.mcdx", cache))
        self.assertIn("exact-boolean", self.part(older / "output" / "Master.mcdx", cache))

        shutil.rmtree(older)
        newer = self.project({})
        build_project(newer)
        self.assertIn("symbolic-engine", self.part(newer / "output" / "Master.mcdx", cache))

    def test_unknown_prime_version_is_explained(self):
        folder = self.project({"prime_version": "11"})
        with self.assertRaisesRegex(ProjectError, "capture_skeleton"):
            load_project(folder)

    def test_prime_version_defaults_to_12(self):
        self.assertEqual(load_project(self.project({})).prime_version, "12")


class VersionStampsTest(unittest.TestCase):
    def test_bundled_skeleton_describes_its_schema_versions(self):
        description = prime_skeleton.describe_versions("12")
        self.assertIn("Prime 12.0.1.0", description)
        self.assertIn("Worksheet 5.11.2", description)

    def test_missing_skeleton_names_what_is_available(self):
        with self.assertRaisesRegex(prime_skeleton.SkeletonError, "available: .*12"):
            prime_skeleton.load_skeleton("3")


if __name__ == "__main__":
    unittest.main()
