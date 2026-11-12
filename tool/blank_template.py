"""Disciplines without a CSV: a blank template to fill in Prime, and how the master reads the result.

The tool writes the blank worksheet once and never overwrites it afterwards, so calculations written in Prime
are safe when the project is rebuilt. The master's combined summary lists the outputs the author designated in
that file (Input/Output > Assign Outputs).
"""
from __future__ import annotations

from pathlib import Path

from mcdx_build import GRID, Frame, Sheet
from mcdx_results import DesignatedOutput, WorksheetReadError, read_designated_outputs
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
from project_config import Discipline, ProjectConfig, ProjectInfo
from rich_text import Run

BLANK_SECTION_TITLE = "Calculations"
BLANK_SECTION_TAG = "calc_calculations"  # the master's contents link here, so keep it if you restructure the file
BLANK_AREA_INNER_HEIGHT = 220.0          # px of free space inside the empty calculation area
HINT_X, HINT_WIDTH = 20.0, 590.0

CALCULATION_HINT = ("Write this discipline's calculations here (delete this note). To show a result in the "
                    "master's combined summary, select it and use Input/Output > Assign Outputs, then save the "
                    "file and rebuild the project.")
SUMMARY_HINT = "Key results for this discipline can be listed here."


def build_blank_discipline(d: Discipline, info: ProjectInfo, master_file: str) -> Sheet:
    """Title block, contents, an empty tagged calculation area and a summary heading."""
    sheet = Sheet()
    add_header_and_footer(sheet, info, d.name)
    add_title_block(sheet, info, f"{d.name} Calculations", info.name)

    sheet.skip(20)
    sheet.text("Contents", style="Heading 1")
    sheet.text([Run(BLANK_SECTION_TITLE, f"#{BLANK_SECTION_TAG}")])
    sheet.text([Run("Summary", f"#{SUMMARY_TAG}")])
    sheet.text([Run("Back to master contents", f"{master_file}.mcdx#{MASTER_CONTENTS_TAG}")])
    sheet.page_break()

    sheet.text(BLANK_SECTION_TITLE, style="Heading 1", tag=f"h_{BLANK_SECTION_TAG}")
    area = Frame(sheet)
    area.text(CALCULATION_HINT, top=GRID * 2, left=HINT_X, width=HINT_WIDTH)
    area.y = BLANK_AREA_INNER_HEIGHT
    sheet.area_from_frame(BLANK_SECTION_TAG, area)
    sheet.text([Run("Back to contents", f"#{TITLE_TAG}")])
    sheet.skip(10)

    sheet.ensure_space(SUMMARY_MIN_SPACE)
    sheet.text("Summary", style="Heading 1", tag=SUMMARY_TAG)
    sheet.text(SUMMARY_HINT)
    return sheet


def select_outputs(outputs: list[DesignatedOutput], wanted: list[str] | None) -> list[DesignatedOutput]:
    """All outputs, or only those whose variable name or alias is in `wanted`."""
    if wanted is None:
        return outputs
    return [o for o in outputs if o.variable in wanted or o.alias in wanted]


def write_blank_discipline(d: Discipline, cfg: ProjectConfig, out: Path) -> tuple[list[DesignatedOutput], list[str]]:
    """Create the blank worksheet unless the file already exists, then read its designated outputs.

    Returns (the outputs to show in the master's summary, the lines for the import report).
    """
    path = out / f"{d.file}.mcdx"
    if path.exists():
        lines = [f"{d.name}  (no CSV): kept existing {path.name} - not overwritten"]
    else:
        build_blank_discipline(d, cfg.info, cfg.master_file).save(path)
        lines = [f"{d.name}  (no CSV): created blank template {path.name}"]
    try:
        outputs = select_outputs(read_designated_outputs(path), d.summary)
    except WorksheetReadError as e:
        return [], lines + [f"    note: {e}; this discipline has no lines in the combined summary"]
    return outputs, lines + [f"    designated outputs found: {len(outputs)}"]


def place_designated_outputs(sheet: Sheet, d: Discipline, outputs: list[DesignatedOutput]) -> None:
    """Summary lines for a hand-written discipline: each designated output as `alias ... name = value`."""
    if not outputs:
        sheet.text(f"No designated outputs found in {d.file}.mcdx yet. In Prime, select a result, choose "
                   "Input/Output > Assign Outputs, save the file and rebuild.", width=FULL_WIDTH)
        return
    for output in outputs:
        sheet.text(output.alias, width=SUMMARY_LABEL_WIDTH, advance=False)  # the value goes on the same row
        sheet.evaluate(output.variable, left=SUMMARY_VALUE_X, override_xml=output.unit_override_xml)


def find_name_clashes(names_by_file: dict[str, set[str]]) -> list[str]:
    """Messages for variable names used by more than one discipline.

    The master includes every discipline file into one namespace, so a name defined in two of them silently takes
    the value of whichever is included last.
    """
    owners: dict[str, list[str]] = {}
    for file, names in names_by_file.items():
        for name in names:
            owners.setdefault(name, []).append(file)
    return [f"variable '{name}' is used in more than one discipline ({', '.join(files)}); "
            "the master shares one namespace, so one value will override the other"
            for name, files in sorted(owners.items()) if len(files) > 1]
