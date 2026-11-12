"""Export a project's worksheets to PDF through Mathcad Prime.

    python export_pdf.py [project folder]      ->  <project>/pdf/<name>.pdf
"""
from __future__ import annotations

import sys

from prime_com import PrimeError, prime_session
from project_io import resolve_project


def main() -> None:
    folder = resolve_project(sys.argv[1] if len(sys.argv) > 1 else None)
    files = sorted((folder / "output").glob("*.mcdx"))
    if not files:
        sys.exit("No worksheets found - run build.bat first.")
    out = folder / "pdf"
    out.mkdir(exist_ok=True)

    print(f"Exporting {len(files)} worksheets to PDF through Mathcad Prime...\n")
    try:
        with prime_session() as prime:
            for f in files:
                try:
                    with prime.open_worksheet(f) as worksheet:
                        worksheet.SaveAs(str(out / f"{f.stem}.pdf"))  # the extension selects the format
                    print(f"  {out / (f.stem + '.pdf')}")
                except PrimeError as e:
                    print(f"  {f.name}: {e}")
    except PrimeError as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
