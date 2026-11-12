"""Read calculated results out of a worksheet saved by Mathcad Prime, keyed by variable name."""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

NS = {
    "ws": "http://schemas.mathsoft.com/worksheet50",
    "ml": "http://schemas.mathsoft.com/math50",
    "u": "http://schemas.mathsoft.com/units10",
    "r": "http://schemas.mathsoft.com/result10",
}

Result = tuple[float, str]  # (value in SI base units, unit name or "")


def _numeric_results(result_xml: bytes) -> dict[str, Result]:
    """result-id -> (value, unit) for every result that is a single real number."""
    values = {}
    for data in etree.fromstring(result_xml).findall("r:resultData", NS):
        number = data.find(".//ml:real", NS)
        if number is None:
            continue
        unit = data.find(".//u:unitReference", NS)
        values[data.get("result-id")] = (float(number.text), unit.get("unit") if unit is not None else "")
    return values


def read_results(mcdx: Path) -> dict[str, Result]:
    """{variable name: (value, unit)} for every displayed result in the worksheet.

    A math region points at its result through `resultRef`; the variable is the first identifier inside the
    region's definition or evaluation.
    """
    with zipfile.ZipFile(mcdx) as package:
        worksheet = etree.fromstring(package.read("mathcad/worksheet.xml"))
        results = _numeric_results(package.read("mathcad/result.xml"))

    named = {}
    for region in worksheet.iterfind(".//ws:math", NS):
        result_id = region.get("resultRef")
        if result_id not in results:
            continue
        statement = next((c for c in region if c.tag.endswith(("}define", "}eval"))), None)
        identifier = statement.find("ml:id", NS) if statement is not None else None
        if identifier is not None and identifier.text:
            named[identifier.text] = results[result_id]
    return named
