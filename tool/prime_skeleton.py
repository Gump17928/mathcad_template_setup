"""The Prime-version-specific parts that every generated worksheet copies unchanged.

A skeleton is a worksheet saved by a real Mathcad Prime, reduced to six parts: the document properties (which
carry the version stamps), the settings, and the package plumbing. Generated worksheets reuse them so that they look
like files written by that Prime version, which is what an older Prime needs in order to accept them.

Skeletons live in `skeleton/prime<major>.mcdx`. `capture_skeleton.py` makes one from a worksheet saved by any Prime.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SKELETON_DIR = Path(__file__).parent / "skeleton"
DEFAULT_VERSION = "12"
NEUTRAL_AUTHOR = "MathCAD Template Generator"

CONTENT_TYPES = "[Content_Types].xml"
PACKAGE_RELS = "_rels/.rels"
APP_PROPERTIES = "docProps/app.xml"
CORE_PROPERTIES = "docProps/core.xml"
PRESENTATION = "mathcad/settings/presentation.xml"
CALCULATION = "mathcad/settings/calculation.xml"
SKELETON_PARTS = (CONTENT_TYPES, PACKAGE_RELS, APP_PROPERTIES, CORE_PROPERTIES, PRESENTATION, CALCULATION)

# What the generator writes into an included worksheet's cached settings, if the skeleton's Prime knows the setting.
INCLUDE_BEHAVIOR = {
    "exact-boolean": "true",
    "units-in-symbolics": "true",
    "constants-in-symbolics": "true",
    "symbolic-engine": "axiom",
}

# Namespaces the generator writes; a sample that uses others was saved by a Prime it cannot imitate.
EXPECTED_NAMESPACES = {
    "mathcad/worksheet.xml": ("http://schemas.mathsoft.com/worksheet50", "http://schemas.mathsoft.com/math50"),
    "mathcad/result.xml": ("http://schemas.mathsoft.com/result10",),
    "mathcad/integration.xml": ("http://schemas.ptc.com/integration10",),
    CALCULATION: ("http://schemas.ptc.com/mathcad/settings/calculation10",),
}


class SkeletonError(Exception):
    """A skeleton is missing or a sample worksheet cannot be used; the message says what to do."""


@dataclass(frozen=True)
class Skeleton:
    version: str
    parts: dict[str, bytes]

    def include_behavior(self) -> dict[str, str]:
        """`calculationBehavior` attributes for an include cache, limited to those this Prime version writes."""
        calculation = self.parts[CALCULATION].decode("utf-8-sig")
        present = set(re.findall(r'(\S+?)="', re.search(r"<calculationBehavior([^>]*)>", calculation).group(1)))
        return {name: value for name, value in INCLUDE_BEHAVIOR.items() if name in present}


def skeleton_path(version: str) -> Path:
    return SKELETON_DIR / f"prime{version}.mcdx"


def available_versions() -> list[str]:
    """Prime major versions that have a skeleton, newest first."""
    found = [p.stem.removeprefix("prime") for p in SKELETON_DIR.glob("prime*.mcdx")]
    return sorted((v for v in found if v.isdigit()), key=int, reverse=True)


@cache
def load_skeleton(version: str) -> Skeleton:
    path = skeleton_path(version)
    if not path.exists():
        have = ", ".join(available_versions()) or "none"
        raise SkeletonError(
            f"There is no skeleton for Mathcad Prime {version} (available: {have}). Save a worksheet from Prime "
            f"{version} and run capture_skeleton.bat on it - see the README, 'Using an older Prime'.")
    with zipfile.ZipFile(path) as package:
        return Skeleton(version, {name: package.read(name) for name in SKELETON_PARTS})


# ---------------------------------------------------------------- capturing a skeleton from a sample worksheet
def _text(package: zipfile.ZipFile, name: str) -> str:
    try:
        return package.read(name).decode("utf-8-sig")
    except KeyError:
        raise SkeletonError(
            f"the sample has no '{name}' part, so it is not a worksheet this tool can imitate") from None


def sample_version(sample: Path) -> str:
    """Prime major version a sample worksheet was saved by, e.g. '10'."""
    try:
        with zipfile.ZipFile(sample) as package:
            app = _text(package, APP_PROPERTIES)
    except zipfile.BadZipFile:
        raise SkeletonError(f"{sample.name} is not a Mathcad worksheet (it is not a valid .mcdx package)") from None
    match = re.search(r"<appVersion>(\d+)\.", app)
    if not match:
        raise SkeletonError(f"{sample.name}: cannot find the Prime version in docProps/app.xml")
    return match.group(1)


def _structure_problems(package: zipfile.ZipFile) -> list[str]:
    """Header/footer, text regions and content-type entries that the generator relies on."""
    rels, types = _text(package, PACKAGE_RELS), _text(package, CONTENT_TYPES)
    problems = []
    if "header.xml" not in rels or "footer.xml" not in rels:
        problems.append("the sample has no header and footer - in Prime add some text to both, then save again")
    if 'Extension="XamlPackage"' not in types:
        problems.append("the sample has no text regions - type some text into the worksheet, then save again")
    problems += [f"content types do not list {name}"
                 for name in ("/mathcad/integration.xml", "/mathcad/result.xml") if name not in types]
    return problems


def _namespace_problems(package: zipfile.ZipFile) -> list[str]:
    """Parts written in a different XML dialect than the generator produces."""
    problems = []
    for part, namespaces in EXPECTED_NAMESPACES.items():
        if part in package.namelist():
            content = _text(package, part)
            problems += [f"{part} does not use the expected namespace {n}" for n in namespaces if n not in content]
    return problems


def check_sample(sample: Path) -> list[str]:
    """Problems that would make the sample unusable, as a list of messages; empty when it is fine."""
    with zipfile.ZipFile(sample) as package:
        missing = [f"missing part {name}" for name in SKELETON_PARTS if name not in package.namelist()]
        if missing:
            return missing
        return _structure_problems(package) + _namespace_problems(package)


def capture_skeleton(sample: Path, replace: bool = False) -> Path:
    """Write skeleton/prime<major>.mcdx from `sample`, with the author names made neutral. Returns its path."""
    version = sample_version(sample)
    problems = check_sample(sample)
    if problems:
        raise SkeletonError(f"{sample.name} cannot be used:\n  - " + "\n  - ".join(problems))
    destination = skeleton_path(version)
    if destination.exists() and not replace:
        raise SkeletonError(f"{destination.name} already exists. Use --replace to overwrite it.")

    with zipfile.ZipFile(sample) as package:
        parts = {name: package.read(name) for name in SKELETON_PARTS}
    core = parts[CORE_PROPERTIES].decode("utf-8-sig")
    core = re.sub(r"(<dc:creator[^>]*>)[^<]*", rf"\g<1>{NEUTRAL_AUTHOR}", core)
    core = re.sub(r"(<cp:lastModifiedBy>)[^<]*", rf"\g<1>{NEUTRAL_AUTHOR}", core)
    parts[CORE_PROPERTIES] = core.encode("utf-8")

    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as out:
        for name in SKELETON_PARTS:
            out.writestr(name, parts[name])
    return destination


def describe_versions(version: str) -> str:
    """The version stamps inside a skeleton, for comparing what two Prime versions write."""
    app = load_skeleton(version).parts[APP_PROPERTIES].decode("utf-8-sig")
    app_version = re.search(r"<appVersion>([^<]*)", app).group(1)
    schemas = ", ".join(f"{n} {v}" for n, v in re.findall(r'<schemaProperties name="([^"]+)" version="([^"]+)"', app))
    return f"Prime {app_version}: {schemas}"
