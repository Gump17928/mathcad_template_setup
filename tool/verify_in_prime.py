"""Open a project's generated worksheets in Prime and report designated inputs/outputs and calculated results.

    python verify_in_prime.py [project folder]
"""
from __future__ import annotations

import sys

from mcdx_results import read_results
from prime_com import PrimeError, prime_session
from project_io import resolve_project


def main() -> None:
    folder = resolve_project(sys.argv[1] if len(sys.argv) > 1 else None)
    files = sorted((folder / "output").glob("*.mcdx"))
    if not files:
        sys.exit("No worksheets found - run build.bat first.")
    scratch = folder / "_work"  # Prime saves calculated copies here; they are what we read the results from
    scratch.mkdir(exist_ok=True)

    print(f"Opening {len(files)} worksheets from {folder.name} in Mathcad Prime (this takes a minute)...\n")
    failures = 0
    try:
        with prime_session() as prime:
            for f in files:
                print("==", f.name)
                try:
                    with prime.open_worksheet(f) as worksheet:
                        print(f"   designated inputs: {worksheet.Inputs.Count}, outputs: {worksheet.Outputs.Count}")
                        worksheet.SaveAs(str(scratch / f.name))
                except PrimeError as e:
                    print(f"   FAILED: {e}")
                    failures += 1
                    continue
                for name, (value, unit) in read_results(scratch / f.name).items():
                    print(f"   {name} = {value:.6g} {unit}")
    except PrimeError as e:
        sys.exit(f"ERROR: {e}")
    print("\nAll worksheets opened." if not failures else f"\n{failures} worksheet(s) failed to open.")


if __name__ == "__main__":
    main()
