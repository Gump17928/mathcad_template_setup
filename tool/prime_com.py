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
# Newest first. An older Prime may not have the newest interface; all of them have Close, Synchronize and SaveAs.
WORKSHEET_INTERFACES = ("IMathcadPrimeWorksheet3", "IMathcadPrimeWorksheet2")
SAVE_OPTION_DISCARD = 2      # SaveOption.spDiscardChanges in Prime's type library
CALCULATION_WAIT_SECONDS = 4  # Synchronize() returns before every region has finished calculating
OPEN_ATTEMPTS = 3
OPEN_RETRY_SECONDS = 6       # a cold-starting Prime can answer Open() with nothing while it is still loading


class PrimeError(Exception):
    """Prime could not do what was asked; the message says what to try."""


def _as_worksheet(worksheet):
    """The worksheet through the newest interface this Prime supports (the default one lacks Close/SaveAs)."""
    for name in WORKSHEET_INTERFACES:
        try:
            return CastTo(worksheet, name)
        except Exception:  # noqa: BLE001, S110 - a missing interface raises various COM errors; try the next one
            continue
    return worksheet


class PrimeSession:
    """A running Prime. Create it with `prime_session()`."""
    def __init__(self, app):
        self._app = app

    def _open(self, path: Path):
        """`Application.Open`, retried: while Prime is still starting it can return None even though it goes on to
        open the file. A file Prime cannot parse also gives None, and that is reported after the last attempt.

        The path is expanded to its long form first: given a Windows short (8.3) path such as C:\\Users\\FORRES~1\\...
        Prime opens the file but returns None, so every worksheet would look as if it had failed to open."""
        long_path = str(path.resolve())
        for attempt in range(OPEN_ATTEMPTS):
            worksheet = self._app.Open(long_path)
            if worksheet is not None:
                return worksheet
            if attempt < OPEN_ATTEMPTS - 1:
                time.sleep(OPEN_RETRY_SECONDS)
        return None

    @contextmanager
    def open_worksheet(self, path: Path) -> Iterator:
        """Open a worksheet, wait for it to calculate, and close it (discarding changes) afterwards."""
        worksheet = self._open(path)
        if worksheet is None:
            raise PrimeError(f"Prime could not open {path.name} - the file is probably invalid; rebuild it")
        worksheet = _as_worksheet(worksheet)
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
