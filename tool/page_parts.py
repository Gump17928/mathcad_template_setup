"""Parts every generated sheet shares: header and footer, title block, and the link targets used between sheets."""
from __future__ import annotations

from mcdx_build import Sheet
from project_config import ProjectInfo

TITLE_TAG = "top"                # every discipline sheet's title block; "Back to contents" links here
MASTER_CONTENTS_TAG = "contents"
SUMMARY_TAG = "summary"

TITLE_WIDTH = 740
FULL_WIDTH = 700
SUMMARY_LABEL_WIDTH = 260
SUMMARY_VALUE_X = 320
SUMMARY_MIN_SPACE = 200.0        # start a new page for a summary when less than this is left


def add_header_and_footer(sheet: Sheet, info: ProjectInfo, page_title: str) -> None:
    sheet.header_text(f"{info.name} - {page_title}")
    sheet.footer_text(f"{info.number}  Rev {info.revision}")


def add_title_block(sheet: Sheet, info: ProjectInfo, heading: str, subtitle: str) -> None:
    """Title, subtitle and project details at the top of a sheet. The title carries the TITLE_TAG link target."""
    sheet.text(heading, style="Title", tag=TITLE_TAG, width=TITLE_WIDTH)
    sheet.text(subtitle, style="Subtitle", width=TITLE_WIDTH)
    sheet.skip(10)
    sheet.text(f"Project: {info.name}   ({info.number})")
    if info.client:
        sheet.text(f"Client: {info.client}")
    sheet.text(f"Revision: {info.revision}      Date: {info.date}      Author: {info.author}")
