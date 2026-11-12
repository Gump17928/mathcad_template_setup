"""Build the Mathcad worksheets for a project folder.

    python build_template.py [project folder] [--open]

Reads <project>/project.json and writes <project>/output/*.mcdx: one worksheet per discipline plus a master
worksheet (title page, contents, combined summary). A discipline with a CSV is generated from it every time;
a discipline without one gets a blank template the first time, which is then left alone so that calculations
written in Prime are never overwritten.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from blank_template import (
    BLANK_SECTION_TAG,
    BLANK_SECTION_TITLE,
    find_name_clashes,
    place_designated_outputs,
    write_blank_discipline,
)
from csv_import import CsvError, DisciplineModel, Row, RowKind, Section, SummaryKind, load_discipline
from mcdx_build import GRID, MATH_REGION_HEIGHT, TOP_MARGIN, Frame, IoKind, Sheet, snap
from mcdx_results import DesignatedOutput
from page_parts import (
    FULL_WIDTH,
    MASTER_CONTENTS_TAG,
    SUMMARY_LABEL_WIDTH,
    SUMMARY_MIN_SPACE,
    SUMMARY_TAG,
    SUMMARY_VALUE_X,
    TITLE_TAG,
    add_header_and_footer,
    add_title_block,
)
from project_config import Discipline, ProjectConfig, ProjectError, ProjectInfo, load_project
from project_io import resolve_project
from rich_text import Run, text_height

# ---- layout of a calculation block, in px (positions are relative to the Area that holds the block)
LABEL_X, LABEL_WIDTH = 20.0, 200.0
VALUE_X = 235.0              # math regions
VALUE_TEXT_WIDTH = 330       # text shown instead of a math region
NOTE_WIDTH = 590.0
RESULT_OFFSET = 33.6         # a live formula's result is shown this far below its definition
ROW_PADDING = 8.0            # space under each row
NOTE_GAP = 2.0               # space between a row and its note
MAX_AREA_HEIGHT = 700.0      # an Area cannot split across pages; leaves room for the section heading above it
HEADING_ALLOWANCE = 60.0     # space kept for a section heading when deciding if the first Area fits on the page

MISSING_PAGE = "?"
MASTER_SUMMARY_NOTE = ("Values below come from each discipline worksheet through Include regions. "
                       "After changing a discipline file, click the refresh button on its Include to update them.")


# ---------------------------------------------------------------- calculation rows
def row_extent(row: Row) -> float:
    """Height a row occupies, before rounding up to the grid: its main line plus its note."""
    height = max(text_height(row.label, "Normal", LABEL_WIDTH), MATH_REGION_HEIGHT)
    if row.kind == RowKind.CALC:
        height = max(height, RESULT_OFFSET + MATH_REGION_HEIGHT)
    elif row.kind == RowKind.TEXT and row.value:
        height = max(height, text_height(row.value, "Normal", VALUE_TEXT_WIDTH))
    if row.note:
        height += NOTE_GAP + text_height(row.note, "Normal", NOTE_WIDTH)
    return height + ROW_PADDING


def place_row(sheet: Sheet, frame: Frame, row: Row) -> None:
    """Lay out one CSV row inside an area: label on the left, value on the right, note underneath."""
    top = frame.y
    frame.text(row.label, top=top, left=LABEL_X, width=LABEL_WIDTH)
    main_height = max(text_height(row.label, "Normal", LABEL_WIDTH), MATH_REGION_HEIGHT)

    if row.kind in (RowKind.INPUT, RowKind.STATIC):
        region = frame.define(row.name, row.value, row.unit, top=top, left=VALUE_X)
        if row.kind == RowKind.INPUT:
            sheet.designate(region, IoKind.INPUT, row.name)
    elif row.kind == RowKind.CALC:
        frame.define(row.name, row.expr, top=top, left=VALUE_X)
        region = frame.evaluate(row.name, row.unit, top=top + RESULT_OFFSET, left=VALUE_X)
        sheet.designate(region, IoKind.OUTPUT, row.name)
        main_height = max(main_height, RESULT_OFFSET + MATH_REGION_HEIGHT)
    elif row.value:
        frame.text(row.value, top=top, left=VALUE_X, width=VALUE_TEXT_WIDTH)
        main_height = max(main_height, text_height(row.value, "Normal", VALUE_TEXT_WIDTH))

    bottom = top + main_height
    if row.note:
        frame.text(row.note, top=bottom + NOTE_GAP, left=LABEL_X, width=NOTE_WIDTH)
        bottom += text_height(row.note, "Normal", NOTE_WIDTH) + NOTE_GAP
    frame.y = snap(bottom + ROW_PADDING)


def split_into_areas(rows: list[Row]) -> list[list[Row]]:
    """Group rows so that each group fits in one Area (which cannot be split across pages)."""
    groups: list[list[Row]] = [[]]
    used = TOP_MARGIN
    for row in rows:
        height = snap(row_extent(row))
        if used + height > MAX_AREA_HEIGHT and groups[-1]:
            groups.append([])
            used = TOP_MARGIN
        groups[-1].append(row)
        used += height
    return groups


def place_section(sheet: Sheet, section: Section) -> None:
    """A section heading followed by its rows in one or more tagged Areas."""
    groups = split_into_areas(section.rows)
    first_area_height = TOP_MARGIN + sum(snap(row_extent(r)) for r in groups[0]) + GRID * 2
    sheet.ensure_space(HEADING_ALLOWANCE + first_area_height)  # keep the heading with its first area
    sheet.text(section.title, style="Heading 1", tag=f"h_{section.tag}")
    for number, rows in enumerate(groups, start=1):
        frame = Frame(sheet)
        for row in rows:
            place_row(sheet, frame, row)
        sheet.area_from_frame(section.tag if number == 1 else f"{section.tag}_{number}", frame)
    sheet.text([Run("Back to contents", f"#{TITLE_TAG}")])
    sheet.skip(10)


def place_summary(sheet: Sheet, model: DisciplineModel) -> None:
    """One line per summary item: live results as `label ... name = value`, checks as `label: status`."""
    for item in model.summary:
        if item.kind == SummaryKind.RESULT:
            sheet.text(item.label, width=SUMMARY_LABEL_WIDTH, advance=False)  # the value goes on the same row
            sheet.evaluate(item.name, item.unit, left=SUMMARY_VALUE_X)
        else:
            sheet.text(f"{item.label}:  {item.status}", width=FULL_WIDTH)


# ---------------------------------------------------------------- the worksheets
def page_note(pages: dict[str, int], tag: str) -> str:
    return f"   (page {pages.get(tag, MISSING_PAGE)})"


def build_discipline(d: Discipline, model: DisciplineModel, info: ProjectInfo, master_file: str,
                     pages: dict[str, int]) -> Sheet:
    """`pages` maps tag -> page number found by an earlier layout pass (empty on the first pass)."""
    sheet = Sheet()
    add_header_and_footer(sheet, info, d.name)
    add_title_block(sheet, info, f"{d.name} Calculations", info.name)

    sheet.skip(20)
    sheet.text("Contents", style="Heading 1")
    for section in model.sections:
        sheet.text([Run(section.title, f"#{section.tag}"), page_note(pages, section.tag)])
    sheet.text([Run("Summary", f"#{SUMMARY_TAG}"), page_note(pages, SUMMARY_TAG)])
    sheet.text([Run("Back to master contents", f"{master_file}.mcdx#{MASTER_CONTENTS_TAG}")])
    sheet.page_break()

    for section in model.sections:
        place_section(sheet, section)

    sheet.ensure_space(SUMMARY_MIN_SPACE)
    sheet.text("Summary", style="Heading 1", tag=SUMMARY_TAG)
    place_summary(sheet, model)
    return sheet


def build_master(cfg: ProjectConfig, models: dict[str, DisciplineModel], pages_by_file: dict[str, dict[str, int]],
                 sheets: dict[str, Sheet], outputs_by_file: dict[str, list[DesignatedOutput]]) -> Sheet:
    """Title page, contents linking into every discipline sheet, and a combined summary fed by Include regions.

    A discipline in `models` came from a CSV; any other is a blank template whose calculations were written in
    Prime, so its summary lines are the outputs designated in its file (`outputs_by_file`).
    """
    sheet = Sheet()
    add_header_and_footer(sheet, cfg.info, "Master")
    add_title_block(sheet, cfg.info, cfg.info.name, "Engineering Calculation Package")
    sheet.page_break()

    sheet.text("Contents", style="Heading 1", tag=MASTER_CONTENTS_TAG)
    for d in cfg.disciplines:
        sheet.skip(10)
        sheet.text([Run(d.name, f"{d.file}.mcdx#{TITLE_TAG}")], style="Heading 2")
        if d.file in models:
            for section in models[d.file].sections:
                note = page_note(pages_by_file[d.file], section.tag)
                sheet.text(["      ", Run(section.title, f"{d.file}.mcdx#{section.tag}"), note])
        else:  # page numbers are omitted: the file will change once someone writes calculations in it
            sheet.text(["      ", Run(BLANK_SECTION_TITLE, f"{d.file}.mcdx#{BLANK_SECTION_TAG}")])
    sheet.skip(10)
    sheet.text([Run("Combined summary", f"#{SUMMARY_TAG}")], style="Heading 2")
    sheet.page_break()

    sheet.text("Combined summary", style="Heading 1", tag=SUMMARY_TAG)
    sheet.text(MASTER_SUMMARY_NOTE)
    for d in cfg.disciplines:
        sheet.ensure_space(SUMMARY_MIN_SPACE)
        sheet.text([Run(d.name, f"{d.file}.mcdx#{SUMMARY_TAG}")], style="Heading 2")
        if d.file in models:
            sheet.include(f"{d.file}.mcdx", sheets[d.file])
            place_summary(sheet, models[d.file])
        else:
            sheet.include(f"{d.file}.mcdx")  # no cached copy: Prime then reads the live file
            place_designated_outputs(sheet, d, outputs_by_file[d.file])
    return sheet


# ---------------------------------------------------------------- the whole project
def describe(d: Discipline, model: DisciplineModel) -> list[str]:
    """The lines of the import report for one discipline."""
    rows = [r for s in model.sections for r in s.rows]
    count = {kind: sum(r.kind == kind for r in rows) for kind in RowKind}
    lines = [f"{d.name}  ({d.csv}): {len(rows)} rows - {count[RowKind.CALC]} live formulas, "
             f"{count[RowKind.INPUT]} inputs, {count[RowKind.STATIC]} fixed values, {count[RowKind.TEXT]} text rows"]
    return lines + [f"    note: {w}" for w in model.warnings]


def lay_out_discipline_sheets(cfg: ProjectConfig, models: dict[str, DisciplineModel]
                              ) -> tuple[dict[str, Sheet], dict[str, dict[str, int]]]:
    """Lay out the sheet of every CSV discipline. Contents pages quote page numbers that are only known once a
    sheet has been laid out, so each sheet is built twice and the second pass uses the numbers found in the first."""
    pages_by_file: dict[str, dict[str, int]] = {}
    sheets: dict[str, Sheet] = {}
    for _ in range(2):
        for d in cfg.disciplines:
            if d.file in models:
                sheet = build_discipline(d, models[d.file], cfg.info, cfg.master_file, pages_by_file.get(d.file, {}))
                pages_by_file[d.file] = sheet.tags
                sheets[d.file] = sheet
    return sheets, pages_by_file


def build_project(folder: Path) -> list[Path]:
    """Build every worksheet for the project in `folder`. Returns the files in the output folder."""
    cfg = load_project(folder)
    out = folder / "output"

    models: dict[str, DisciplineModel] = {}
    report: dict[str, list[str]] = {}
    for d in cfg.disciplines:
        if d.csv:
            models[d.file] = load_discipline(folder / d.csv, d.key + "_", d.section_titles, d.summary)
            report[d.file] = describe(d, models[d.file])

    sheets, pages_by_file = lay_out_discipline_sheets(cfg, models)

    written: list[Path] = []
    outputs: dict[str, list[DesignatedOutput]] = {}
    for d in cfg.disciplines:
        written.append(out / f"{d.file}.mcdx")
        if d.file in models:
            sheets[d.file].save(written[-1])
        else:
            outputs[d.file], report[d.file] = write_blank_discipline(d, cfg, out)

    master = out / f"{cfg.master_file}.mcdx"
    build_master(cfg, models, pages_by_file, sheets, outputs).save(master)
    written.append(master)

    names = {file: {r.name for s in m.sections for r in s.rows if r.name} for file, m in models.items()}
    names.update({file: {o.variable for o in found} for file, found in outputs.items()})
    lines = [line for d in cfg.disciplines for line in report[d.file]]
    lines += [f"note: {clash}" for clash in find_name_clashes(names)]

    (out / "import_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return written


def main() -> None:
    """Command-line entry point: build the chosen project and print what was created."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folder = resolve_project(args[0] if args else None)
    print(f"Project: {folder.name}\n")
    try:
        files = build_project(folder)
    except (ProjectError, CsvError) as e:
        sys.exit(f"\nERROR: {e}")
    print("\nFiles in the output folder:")
    for f in files:
        print(f"  {f}")
    if "--open" in sys.argv:
        os.startfile(folder / "output")


if __name__ == "__main__":
    main()
