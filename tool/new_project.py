"""Interactive wizard: creates projects/<name>/ with a project.json and one starter CSV per discipline."""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

from project_io import PROJECTS, default_key

STANDARD_DISCIPLINES = ["Structural", "Mechanical", "Electrical", "Civil"]
DEFAULT_PROJECT_NUMBER = "P-0001"

STARTER_CSV = """section,label,name,value,unit,equation,substituted,reference,notes,status
INPUTS,Input A,a,10,m,,,,,
INPUTS,Input B,b,2,m,,,,Replace these starter rows with your own calculation,
RESULTS,Area,area,,m^2,area = a*b,,,,
"""


def ask(prompt: str, default: str = "") -> str:
    shown = f" [{default}]" if default else ""
    return input(f"{prompt}{shown}: ").strip() or default


def folder_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "project"


def ask_project_info() -> dict:
    """Ask for the details that go on the title blocks. Only the project name is required."""
    name = ask("Project name")
    while not name:
        name = ask("Project name (required)")
    return {
        "name": name,
        "number": ask("Project number", DEFAULT_PROJECT_NUMBER),
        "revision": ask("Revision", "A"),
        "client": ask("Client"),
        "author": ask("Author"),
        "date": ask("Date", date.today().isoformat()),
    }


def ask_disciplines() -> list[str]:
    """Ask which of the standard disciplines to include, plus any custom ones."""
    print("\nDisciplines:")
    for number, name in enumerate(STANDARD_DISCIPLINES, 1):
        print(f"  {number}) {name}")
    picked = ask("Type the numbers you need, separated by commas", "1,2,3,4")
    chosen = [STANDARD_DISCIPLINES[int(n) - 1] for n in re.findall(r"\d+", picked)
              if 1 <= int(n) <= len(STANDARD_DISCIPLINES)]
    extra = ask("Other disciplines (names separated by commas, or press Enter for none)")
    return chosen + [e.strip() for e in extra.split(",") if e.strip()]


def unique_key(name: str, taken: set[str]) -> str:
    """The discipline's key, made different from every key in `taken` (ELE, EL2, EL3, ...)."""
    base = default_key(name) or "XXX"
    key, number = base, 2
    while key in taken:
        key, number = f"{base[:2]}{number}", number + 1
    taken.add(key)
    return key


def discipline_entries(names: list[str]) -> list[dict]:
    taken: set[str] = set()
    return [{"name": n, "key": unique_key(n, taken), "csv": f"calcs/{folder_name(n)}.csv"} for n in names]


def create_project(folder: Path, info: dict, disciplines: list[dict]) -> None:
    """Write project.json and a starter CSV for each discipline into a new project folder."""
    (folder / "calcs").mkdir(parents=True)
    for d in disciplines:
        (folder / d["csv"]).write_text(STARTER_CSV, encoding="utf-8")
    config = {"project": info, "master_file": "Master", "disciplines": disciplines}
    (folder / "project.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def main() -> None:
    """Ask the questions, create the project folder and say what to do next."""
    print("New project\n-----------")
    info = ask_project_info()
    names = ask_disciplines()
    if not names:
        sys.exit("\nNo disciplines chosen - nothing created.")

    folder = PROJECTS / folder_name(info["number"] if info["number"] != DEFAULT_PROJECT_NUMBER else info["name"])
    if folder.exists():
        sys.exit(f"\nA project folder named '{folder.name}' already exists. Pick a different project number or name.")
    create_project(folder, info, discipline_entries(names))

    print(f"\nCreated {folder}")
    print("\nNext steps:")
    print(f"  1. Open the CSV files in {folder / 'calcs'} (Excel works)")
    print("     and replace the starter rows with your calculations.")
    print("  2. Double-click build.bat and choose this project.")


if __name__ == "__main__":
    main()
