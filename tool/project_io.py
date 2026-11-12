"""Locating project folders, and the naming rules shared by the wizard and the builder."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
PROJECT_FILE = "project.json"
KEY_LENGTH = 3  # variable-name prefix, e.g. ELE for Electrical


def default_key(discipline_name: str) -> str:
    """Variable-name prefix for a discipline: 'Electrical' -> 'ELE'."""
    return "".join(c for c in discipline_name.upper() if c.isalnum())[:KEY_LENGTH]


def default_file_name(discipline_name: str) -> str:
    """Worksheet file name (no extension) for a discipline."""
    return "".join(c for c in discipline_name if c.isalnum() or c in " -_").strip()


def list_projects() -> list[Path]:
    return sorted(p for p in PROJECTS.glob("*") if (p / PROJECT_FILE).exists())


def _choose_interactively(found: list[Path]) -> Path:
    print("Which project?")
    for number, project in enumerate(found, 1):
        print(f"  {number}) {project.name}")
    while True:
        choice = input("Number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(found):
            return found[int(choice) - 1]
        print("  please type one of the numbers above")


def resolve_project(arg: str | None) -> Path:
    """The project folder named by `arg` (a folder, its project.json, or a name under projects/).
    With no argument: the only project, or a numbered choice if there are several."""
    if arg:
        path = Path(arg.strip().strip('"'))
        if path.is_file() and path.name == PROJECT_FILE:
            path = path.parent
        if not (path / PROJECT_FILE).exists() and (PROJECTS / path).exists():
            path = PROJECTS / path
        if not (path / PROJECT_FILE).exists():
            sys.exit(f"ERROR: '{arg}' is not a project folder (no {PROJECT_FILE} inside it).")
        return path.resolve()

    found = list_projects()
    if not found:
        sys.exit("ERROR: no projects found. Run new_project.bat first.")
    return found[0] if len(found) == 1 else _choose_interactively(found)
