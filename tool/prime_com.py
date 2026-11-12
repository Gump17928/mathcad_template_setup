"""Driving Mathcad Prime over COM: open worksheets, let them calculate, save or export them, and always clean up.

    with prime_session() as prime:
        with prime.open_worksheet(path) as worksheet:
            worksheet.SaveAs("copy.mcdx")      # .pdf and .xps work too

Only worksheets opened through the session are closed afterwards (without saving), so other documents the user has
open in Prime are left alone.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from win32com.client import CastTo, gencache

PROGID = "MathcadPrime.Application"
WORKSHEET_INTERFACE = "IMathcadPrimeWorksheet3"
SAVE_OPTION_DISCARD = 2      # SaveOption.spDiscardChanges in Prime's type library
CALCULATION_WAIT_SECONDS = 4  # Synchronize() returns before every region has finished calculating


class PrimeError(Exception):
    """Prime could not do what was asked; the message says what to try."""


class PrimeSession:
    """A running Prime. Create it with `prime_session()`."""
    def __init__(self, app):
        self._app = app

    @contextmanager
    def open_worksheet(self, path: Path) -> Iterator:
        """Open a worksheet, wait for it to calculate, and close it (discarding changes) afterwards."""
        worksheet = self._app.Open(str(path))
        if worksheet is None:
            # Prime returns None rather than raising when it cannot parse the file.
            raise PrimeError(f"Prime could not open {path.name} - the file is probably invalid; rebuild it")
        worksheet = CastTo(worksheet, WORKSHEET_INTERFACE)  # the default interface lacks Close/Synchronize/SaveAs
        try:
            worksheet.Synchronize()
            time.sleep(CALCULATION_WAIT_SECONDS)
            yield worksheet
        finally:
            worksheet.Close(SAVE_OPTION_DISCARD)


@contextmanager
def prime_session() -> Iterator[PrimeSession]:
    """Start (or attach to) Prime. Quit() only closes Prime if nothing else is open in it."""
    try:
        app = gencache.EnsureDispatch(PROGID)
    except Exception as e:  # pywintypes.com_error is not importable on every platform
        raise PrimeError("Mathcad Prime could not be started - is it installed on this PC?") from e
    app.Visible = True
    try:
        yield PrimeSession(app)
    finally:
        app.Quit(SAVE_OPTION_DISCARD)
