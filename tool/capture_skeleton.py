"""Make a skeleton for another Mathcad Prime version from a worksheet saved by that Prime.

    python capture_skeleton.py "C:\\path\\to\\sample.mcdx" [--replace]

The sample can be any small worksheet, as long as it has some text in the worksheet itself, in its header and in its
footer. The skeleton is written to skeleton\\prime<major version>.mcdx; then put  "prime_version": "<major>"  in a
project's project.json to build that project for that Prime version.
"""
from __future__ import annotations

import sys
from pathlib import Path

from prime_skeleton import SkeletonError, available_versions, capture_skeleton, describe_versions, sample_version


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("Drag a worksheet saved by the other Prime onto capture_skeleton.bat, "
                 "or run:  capture_skeleton.bat \"path\\to\\sample.mcdx\"")
    sample = Path(args[0].strip('"'))
    if not sample.exists():
        sys.exit(f"ERROR: {sample} does not exist")
    try:
        version = sample_version(sample)
        path = capture_skeleton(sample, replace="--replace" in sys.argv)
    except SkeletonError as e:
        sys.exit(f"ERROR: {e}")

    print(f"Saved {path.name} (Mathcad Prime {version}).\n")
    print("What each Prime version writes into its worksheets:")
    for v in available_versions():
        print(f"  {describe_versions(v)}")
    print(f'\nNext: add  "prime_version": "{version}"  to the project.json of a project (next to "master_file"), '
          "then run build.bat.")


if __name__ == "__main__":
    main()
