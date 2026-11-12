"""project.json: what a project contains, validated and with defaults filled in."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

from project_io import PROJECT_FILE, default_file_name, default_key


class ProjectError(Exception):
    """A problem in project.json that the user can fix; the message says what."""


@dataclass(frozen=True)
class ProjectInfo:
    """The `project` block of project.json: what appears on every title block and header."""
    name: str
    number: str
    revision: str
    client: str
    author: str
    date: str


@dataclass(frozen=True)
class Discipline:
    """One entry of the `disciplines` list in project.json."""
    name: str
    key: str                  # prefix for variable names, e.g. ELE -> ELE_I_design
    file: str                 # worksheet file name without extension
    csv: str | None = None    # CSV path relative to the project folder; None = blank template to fill in Prime
    section_titles: dict = field(default_factory=dict)
    summary: list | None = None  # variables to list in the summary; None = all live formulas / all designated outputs


@dataclass(frozen=True)
class ProjectConfig:
    info: ProjectInfo
    master_file: str
    disciplines: list[Discipline]


def load_project(folder: Path) -> ProjectConfig:
    """Read and validate <folder>/project.json, filling in defaults for anything optional."""
    try:
        raw = json.loads((folder / PROJECT_FILE).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        message = f"{PROJECT_FILE} is not valid JSON: {e}  (check commas and quotes near line {e.lineno})"
        raise ProjectError(message) from e
    for key in ("project", "disciplines"):
        if key not in raw:
            raise ProjectError(f"{PROJECT_FILE} is missing '{key}'")

    info = ProjectInfo(**{f.name: raw["project"].get(f.name, "") for f in fields(ProjectInfo)})
    disciplines, seen_keys, seen_files = [], set(), set()
    for d in raw["disciplines"]:
        if "name" not in d:
            raise ProjectError(f"every discipline needs a 'name' in {PROJECT_FILE}")
        discipline = Discipline(
            name=d["name"],
            key=d.get("key") or default_key(d["name"]),
            file=d.get("file") or default_file_name(d["name"]),
            csv=d.get("csv") or None,
            section_titles=d.get("section_titles", {}),
            summary=d.get("summary"),
        )
        if discipline.key in seen_keys or discipline.file in seen_files:
            raise ProjectError(f"discipline '{discipline.name}' repeats a key or file name; they must be unique")
        seen_keys.add(discipline.key)
        seen_files.add(discipline.file)
        disciplines.append(discipline)
    return ProjectConfig(info, raw.get("master_file", "Master"), disciplines)
