"""Read a calculation CSV into a discipline model that the worksheet builder can lay out.

Columns (header names are case-insensitive; only `section` and `label` are required):

  section      groups rows into one calculation area (e.g. LOAD, AMPACITY)
  label        description shown next to the value
  name         optional variable name; otherwise taken from "label (name)" or from "name = ..." in equation
  value        number, or text (text rows are shown, not calculated)
  unit         e.g. A, V, kN/m, in^2, ohm/1000ft  (names Prime does not know are kept as a note)
  equation     "I_design = I_RLA * k_cont" -> becomes a live Mathcad formula when it can be, see below
  substituted  the equation with numbers, shown as a note
  nec_ref      code reference (also accepted: reference, ref), shown as a note
  source       extra note (also accepted: notes, note)
  status       PASS / FAIL etc., shown as a note and listed in the summary

An equation becomes a live formula only if it is plain arithmetic (+ - * / ^ and brackets), uses variables that
are defined on earlier rows, and (when the row has a value) agrees with that value within 1 %. Everything else
(table lookups, sqrt, acos, "if", ...) stays a fixed value with its equation shown as a note.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from formula import Node, evaluate, parse, rename_variables, to_text, variables

# Unit names verified to be accepted by Mathcad Prime 12.0.1.0. Names Prime rejects (kVA, kWh, kohm, uF, um, %,
# AWG, kcmil, degC, ...) are not listed, so they are kept as a note instead of becoming part of a formula.
# Add to this only after testing the name in Prime.
VALID_UNITS = frozenset({
    # electrical
    "A", "mA", "kA", "V", "mV", "kV", "W", "kW", "MW", "var", "Hz", "kHz", "ohm", "F", "H", "mH",
    # length and volume
    "m", "mm", "cm", "km", "in", "ft", "yd", "mi", "mil", "L", "gal",
    # force, pressure, mass
    "N", "kN", "MN", "lbf", "kip", "Pa", "kPa", "MPa", "GPa", "psi", "ksi", "bar", "atm", "kg", "g", "lb", "ton",
    # energy, power, time, angle, temperature
    "J", "BTU", "hp", "s", "min", "hr", "day", "rpm", "rad", "deg", "K",
})

REQUIRED_COLUMNS = ("section", "label")
COLUMN_ALIASES = {
    "nec_ref": "reference", "ref": "reference", "reference": "reference",
    "source": "notes", "notes": "notes", "note": "notes",
}
NOTE_COLUMNS = ("reference", "substituted", "notes")  # appended to a row's note, in this order
NOTE_SEPARATOR = "  |  "

# A formula is accepted as live when it reproduces the CSV value to within this relative tolerance.
FORMULA_TOLERANCE = 0.01
_ZERO_GUARD = 1e-12  # keeps the tolerance from collapsing to 0 when the CSV value is 0

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LABEL_NAME = re.compile(r"\(([A-Za-z_][A-Za-z0-9_]*)\)\s*$")  # "Design current (I_design)"
_EQ_LHS = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)")  # "I_design = ..."


class CsvError(Exception):
    """A problem in the CSV that the user can fix; the message says where."""


class RowKind(str, Enum):
    INPUT = "input"    # a number the user can change; registered as a designated Mathcad input
    CALC = "calc"      # a live Mathcad formula; registered as a designated output
    STATIC = "static"  # a number kept as written (its equation, if any, is shown as a note)
    TEXT = "text"      # shown only


class SummaryKind(str, Enum):
    RESULT = "result"  # a live value pulled from the worksheet
    CHECK = "check"    # a status such as PASS, taken from the CSV text


@dataclass
class Row:
    """One CSV row after interpretation, ready to be laid out."""
    section: str
    label: str
    kind: RowKind
    name: str = ""   # Mathcad variable name including the discipline prefix
    value: str = ""
    unit: str = ""   # Prime-valid, or "" if none or not recognised
    expr: str = ""   # live formula text (prefixed names), only for CALC rows
    note: str = ""
    status: str = ""
    line: int = 0    # CSV line number, for messages


@dataclass
class Section:
    key: str    # the CSV section value
    title: str
    tag: str    # Mathcad tag used for links to this section
    rows: list[Row] = field(default_factory=list)


@dataclass
class SummaryItem:
    """One line of a discipline's summary."""
    kind: SummaryKind
    label: str
    name: str = ""
    unit: str = ""
    status: str = ""


@dataclass
class DisciplineModel:
    sections: list[Section]
    summary: list[SummaryItem]
    warnings: list[str]


@dataclass(frozen=True)
class CsvRow:
    """One data line of the CSV with its line number."""

    line: int
    cells: dict[str, str]

    def get(self, column: str) -> str:
        return self.cells.get(column, "")

    @property
    def where(self) -> str:
        return f"line {self.line} ({self.get('label')})"


@dataclass
class _Context:
    """State shared while the rows of one discipline are read, top to bottom."""

    prefix: str                                                   # added to every Mathcad variable name
    warnings: list[str]
    prefixed_names: dict[str, str] = field(default_factory=dict)  # CSV name -> Mathcad name, for rows already read
    values: dict[str, float] = field(default_factory=dict)        # CSV name -> numeric value, for rows already read


# ---------------------------------------------------------------- units and numbers
def normalise_unit(unit: str) -> str | None:
    """'ohm/1000ft' -> 'ohm/(1000*ft)'. '' stays ''. Returns None if Prime would not understand it."""
    u = unit.strip().replace(" ", "")
    if not u:
        return ""
    u = re.sub(r"(\d+)([A-Za-z]+)", r"(\1*\2)", u)
    try:
        parse(u)
    except ValueError:
        return None
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", u))
    return u if names <= VALID_UNITS else None


def _to_float(text: str) -> float | None:
    try:
        return float(text.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- reading the file
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise CsvError(f"CSV file not found: {path}") from None
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1252")  # files saved by older Excel versions


def _read_rows(path: Path) -> list[CsvRow]:
    reader = csv.reader(_read_text(path).splitlines())
    try:
        header = [COLUMN_ALIASES.get(h.strip().lower(), h.strip().lower()) for h in next(reader)]
    except StopIteration:
        raise CsvError(f"{path.name} is empty") from None
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise CsvError(f"{path.name}: first row must be a header containing columns {missing} (found {header})")

    rows = []
    for line, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells) or cells[0].lstrip().startswith("#"):
            continue
        row = CsvRow(line, {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(header)})
        if not row.get("section") or not row.get("label"):
            raise CsvError(f"{path.name} line {line}: 'section' and 'label' must both be filled in")
        rows.append(row)
    if not rows:
        raise CsvError(f"{path.name} has a header but no data rows")
    return rows


def _group_by_section(rows: list[CsvRow]) -> dict[str, list[CsvRow]]:
    """Sections in order of first appearance, because a worksheet reads top to bottom."""
    groups: dict[str, list[CsvRow]] = {}
    for row in rows:
        groups.setdefault(row.get("section"), []).append(row)
    return groups


# ---------------------------------------------------------------- variable names
def _assign_names(rows: list[CsvRow], warnings: list[str]) -> dict[int, str]:
    """CSV line number -> variable name ('' if the row has none). Looks in the `name` column, then in
    'label (name)', then at the left-hand side of the equation."""
    names: dict[int, str] = {}
    used: set[str] = set()
    for row in rows:
        name = row.get("name")
        if not name:
            from_label = _LABEL_NAME.search(row.get("label"))
            from_equation = _EQ_LHS.match(row.get("equation"))
            if from_label and from_label.group(1).lower() != "input":
                name = from_label.group(1)
            elif from_equation:
                name = from_equation.group(1)
        if name and not _IDENT.match(name):
            warnings.append(f"line {row.line}: name '{name}' is not a valid variable name - ignored")
            name = ""
        if name in used:
            warnings.append(f"line {row.line}: name '{name}' used more than once - later row treated as text")
            name = ""
        if name:
            used.add(name)
        names[row.line] = name
    return names


# ---------------------------------------------------------------- one row
def _live_formula(row: CsvRow, name: str, number: float | None,
                  ctx: _Context) -> tuple[str | None, float | None]:
    """Try to turn the row's equation into a live formula.

    Returns (formula text with Mathcad names or None, the row's number - computed from the formula if the CSV had none).
    """
    equation = row.get("equation")
    lhs = _EQ_LHS.match(equation)
    if not lhs or lhs.group(1) != name:
        return None, number
    try:
        tree: Node = parse(equation[lhs.end():])
    except ValueError:
        return None, number
    if not variables(tree) <= set(ctx.prefixed_names):
        return None, number  # refers to something not defined above this row
    try:
        computed = evaluate(tree, ctx.values)
    except (ZeroDivisionError, KeyError, OverflowError, ValueError):
        return None, number

    if number is not None and abs(computed - number) > FORMULA_TOLERANCE * max(abs(number), _ZERO_GUARD):
        ctx.warnings.append(
            f"{row.where}: formula gives {computed:.6g} but the CSV says {row.get('value')} - kept the CSV value "
            f"as a fixed number and showed the equation as a note (expected if the CSV uses % or another scaled unit)"
        )
        return None, number
    return to_text(rename_variables(tree, ctx.prefixed_names)), (computed if number is None else number)


def _numeric_row(row: CsvRow, base: Row, name: str, unit: str, ctx: _Context, notes: list[str]) -> None:
    """Fill in a row that names a variable and has a number or a formula."""
    value_text = row.get("value")
    equation = row.get("equation")
    base.name, base.unit, base.value = ctx.prefix + name, unit, value_text
    live, number = _live_formula(row, name, _to_float(value_text), ctx)

    if live:
        base.kind, base.expr = RowKind.CALC, live
    elif number is None:
        ctx.warnings.append(f"{row.where}: no value and no usable formula - shown as text")
        base.name = ""
        return
    elif not equation or "(input)" in equation:
        base.kind = RowKind.INPUT
    else:
        base.kind = RowKind.STATIC
        notes.append(f"eq: {equation}")

    ctx.prefixed_names[name] = base.name
    ctx.values[name] = number


def _classify_row(row: CsvRow, section: str, name: str, ctx: _Context) -> Row:
    value_text, equation, unit_text = row.get("value"), row.get("equation"), row.get("unit")
    unit = normalise_unit(unit_text)
    unit_note = f"unit: {unit_text}" if unit is None else ""
    unit = unit or ""

    result = Row(section, row.get("label"), RowKind.TEXT, status=row.get("status"), line=row.line)
    notes = [row.get("status")] if row.get("status") else []

    has_number_or_formula = _to_float(value_text) is not None or (not value_text and equation)
    if name and has_number_or_formula:
        _numeric_row(row, result, name, unit, ctx, notes)
    else:
        result.value = f"{value_text} {unit_text}".strip()
        if equation:
            notes.append(f"eq: {equation}")

    if unit_note and result.kind != RowKind.TEXT:
        notes.append(unit_note)
    notes += [row.get(column) for column in NOTE_COLUMNS if row.get(column)]
    result.note = NOTE_SEPARATOR.join(notes)
    return result


# ---------------------------------------------------------------- sections and summary
def _section_tag(key: str, taken: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") or "section"
    while slug in taken:
        slug += "_x"
    taken.add(slug)
    return f"calc_{slug}"


def _build_summary(rows: list[Row], prefix: str, wanted: list[str] | None, warnings: list[str]) -> list[SummaryItem]:
    if wanted is None:
        picked = [r for r in rows if r.kind == RowKind.CALC]
    else:
        by_name = {r.name[len(prefix):]: r for r in rows if r.name}
        picked = []
        for name in wanted:
            found = by_name.get(name) or by_name.get(name.removeprefix(prefix))
            if found is None:
                warnings.append(f"summary lists '{name}' but no row defines that variable")
            else:
                picked.append(found)
    results = [SummaryItem(SummaryKind.RESULT, r.label, r.name, r.unit) for r in picked]
    checks = [SummaryItem(SummaryKind.CHECK, r.label, status=r.status) for r in rows if r.status]
    return results + checks


def load_discipline(path: Path, prefix: str, section_titles: dict | None = None,
                    summary_names: list[str] | None = None) -> DisciplineModel:
    """Read one discipline's CSV.

    prefix         added to every variable name (e.g. 'ELE_') so disciplines can reuse names
    section_titles {CSV section value: friendly title}; otherwise the section value is title-cased
    summary_names  variables to list in the summary; None means every live formula
    """
    titles = {k.upper(): v for k, v in (section_titles or {}).items()}
    warnings: list[str] = []
    groups = _group_by_section(_read_rows(path))
    names = _assign_names([row for rows in groups.values() for row in rows], warnings)

    ctx = _Context(prefix, warnings)
    taken_tags: set[str] = set()
    sections = []
    for key, csv_rows in groups.items():
        title = titles.get(key.upper()) or key.replace("_", " ").title()
        section = Section(key, title, _section_tag(key, taken_tags))
        section.rows = [_classify_row(r, key, names[r.line], ctx) for r in csv_rows]
        sections.append(section)

    all_rows = [row for s in sections for row in s.rows]
    return DisciplineModel(sections, _build_summary(all_rows, prefix, summary_names, warnings), warnings)
