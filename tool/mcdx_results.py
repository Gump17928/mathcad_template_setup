"""Read things back out of a worksheet saved by Mathcad Prime: calculated results, and designated outputs."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

NS = {
    "ws": "http://schemas.mathsoft.com/worksheet50",
    "ml": "http://schemas.mathsoft.com/math50",
    "u": "http://schemas.mathsoft.com/units10",
    "r": "http://schemas.mathsoft.com/result10",
    "i": "http://schemas.ptc.com/integration10",
}

Result = tuple[float, str]  # (value in SI base units, unit name or "")


class WorksheetReadError(Exception):
    """The file is not a worksheet this tool can read; the message says which file."""


@dataclass(frozen=True)
class DesignatedOutput:
    """A region the author marked with Input/Output > Assign Outputs."""

    alias: str            # the name shown in Prime's Input/Output list (usually the variable name)
    variable: str         # the variable the region displays
    unit_override_xml: str  # the unit the result is shown in, as math XML; "" means the result's own units



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


def _statement(math_region):
    """The `define` or `eval` element of a math region (the first thing inside it), or None."""
    return next((c for c in math_region if c.tag.endswith(("}define", "}eval"))), None)


def _unit_override_xml(statement) -> str:
    """The unit an evaluation is displayed in, copied as math XML; "" when it just uses the result's own units."""
    override = statement.find("ml:unitOverride", NS)
    if override is None or override.find("ml:placeholder", NS) is not None:
        return ""
    return "".join(etree.tostring(child, encoding="unicode", with_tail=False) for child in override)


def read_designated_outputs(mcdx: Path) -> list[DesignatedOutput]:
    """Regions the author designated as outputs (Input/Output > Assign Outputs), with the variable each shows.

    Raises WorksheetReadError if the file cannot be read. Outputs whose region is not a plain `name =` are skipped,
    because they cannot be repeated elsewhere by variable name.
    """
    try:
        with zipfile.ZipFile(mcdx) as package:
            worksheet = etree.fromstring(package.read("mathcad/worksheet.xml"))
            integration = etree.fromstring(package.read("mathcad/integration.xml"))
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError, OSError) as e:
        raise WorksheetReadError(f"could not read {mcdx.name} ({e})") from e

    regions = {r.get("region-id"): r for r in worksheet.iterfind(".//ws:region", NS)}
    outputs = []
    for designation in integration.findall("i:region[@ioTagType='Output']", NS):
        region = regions.get(designation.get("region-id"))
        math = region.find("ws:math", NS) if region is not None else None
        statement = _statement(math) if math is not None else None
        identifier = statement.find("ml:id", NS) if statement is not None else None
        if identifier is None or not identifier.text:
            continue
        alias = designation.findtext("i:outputAliases/i:alias", default="", namespaces=NS) or identifier.text
        outputs.append(DesignatedOutput(alias, identifier.text, _unit_override_xml(statement)))
    return outputs
