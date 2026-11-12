"""Generate Mathcad Prime worksheets (.mcdx) from Python.

The XML shapes were taken from a worksheet saved by Prime 12.0.1.0 (skeleton/skeleton.mcdx, which also supplies
the document properties and settings that are copied unchanged):

  tag          tag="..." attribute on a <region>
  heading      <Run style="Heading 1"> inside the text region's XamlPackage
  link         <Hyperlink NavigateUri="#tag"> (or "file.mcdx#tag") inside the XamlPackage
  area         <region><Area AreaHeight="n"><regions>...</regions></Area></region>
  page break   <region><pageBreak/></region>, always placed at the end of its page
  include      <region><reference href="..."/></region> plus a cached copy of the included definitions
  designation  mathcad/integration.xml

Usage: build a `Sheet`, add content top to bottom (text, define, evaluate, area, include, page_break), then save().
"""
from __future__ import annotations

import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from formula import Neg, Node, Num, Parens, Var, parse
from opc import CONTENT_TYPES_PART, XML_DECLARATION, Relationship, new_relationship_id, relationships_xml, write_package
from rich_text import STYLES, WPF_NS, RichText, Run, as_paragraphs, text_height, xaml_package

SKELETON = Path(__file__).parent / "skeleton" / "skeleton.mcdx"
# Parts copied unchanged from the skeleton.
SKELETON_PARTS = (
    CONTENT_TYPES_PART, "_rels/.rels", "docProps/app.xml", "docProps/core.xml",
    "mathcad/settings/presentation.xml", "mathcad/settings/calculation.xml",
)

# XML namespaces
WS_NS = "http://schemas.mathsoft.com/worksheet50"
ML_NS = "http://schemas.mathsoft.com/math50"
UNITS_NS = "http://schemas.mathsoft.com/units10"
RESULT_NS = "http://schemas.mathsoft.com/result10"
INTEGRATION_NS = "http://schemas.ptc.com/integration10"
CALCULATION_NS = "http://schemas.ptc.com/mathcad/settings/calculation10"

# Relationship and content types
REL_FLOW_DOCUMENT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/flowDocument"
REL_INCLUDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/include"
CONTENT_TYPE_INCLUDE = "application/vnd.openxmlformats-officedocument.mathprocessingml.mathcad.include+xml"

# ---- page geometry (US Letter, as Prime lays it out; measured from Prime's own output). All values in px.
PAGE_WIDTH = 816.0
PAGE_CONTENT_HEIGHT = 864.0  # usable height of one page
PAGE_BREAK_HEIGHT = 2.0      # a page-break region occupies this much between pages
GRID = 9.6                   # Prime snaps regions to this grid
TOP_MARGIN = GRID * 4        # where content starts on a page (below the header)
LEFT_MARGIN = 38.4
HEADER_TOP = GRID            # header and footer text sit this far from their own top
DEFAULT_TEXT_WIDTH = 700.0
MATH_REGION_HEIGHT = 25.6    # a one-line math region
MATH_REGION_WIDTH_HINT = 120.0  # Prime recomputes the real width on open
AREA_WIDTH = 624
INCLUDE_REGION_HEIGHT = 20
AREA_PADDING = GRID * 2      # space under the last region inside an area
CACHED_ROW_SPACING = 38.4    # vertical spacing of the cached definitions in an include part


def snap(y: float) -> float:
    """Round `y` up to the next grid line."""
    return math.ceil(y / GRID - 1e-9) * GRID


class IoKind(str, Enum):
    """How a region is exposed to other programs (Prime's Input/Output designation)."""

    INPUT = "Input"
    OUTPUT = "Output"


@dataclass(frozen=True)
class Designation:
    region_id: int
    kind: IoKind
    alias: str


# ---------------------------------------------------------------- math XML
# Element names Prime uses for each operator.
_OPERATOR_ELEMENT = {"+": "plus", "-": "minus", "*": "mult", "/": "div", "^": "pow"}


def _identifier_xml(name: str, label: str = "VARIABLE", contextual: bool = True) -> str:
    ctx = ' label-is-contextual="true"' if contextual else ""
    return f'<ml:id labels="{label}"{ctx} xml:space="preserve">{escape(name)}</ml:id>'


def formula_xml(node: Node, id_label: str = "VARIABLE") -> str:
    """Math XML for a formula tree. Identifiers get `id_label`: VARIABLE for formulas, UNIT for units."""
    if isinstance(node, Num):
        return f"<ml:real>{node.text}</ml:real>"
    if isinstance(node, Var):
        return _identifier_xml(node.name, id_label)
    if isinstance(node, Parens):
        return f"<ml:parens>{formula_xml(node.inner, id_label)}</ml:parens>"
    if isinstance(node, Neg):
        return f"<ml:apply><ml:neg />{formula_xml(node.operand, id_label)}</ml:apply>"
    element = _OPERATOR_ELEMENT[node.op]
    return f"<ml:apply><ml:{element} />{formula_xml(node.left, id_label)}{formula_xml(node.right, id_label)}</ml:apply>"


def unit_xml(unit: str) -> str:
    """Math XML for a unit expression such as 'kN/m' or 'm^2'."""
    return formula_xml(parse(unit), "UNIT")


def _with_unit(value_xml: str, unit: str) -> str:
    return f"<ml:apply><ml:scale />{value_xml}{unit_xml(unit)}</ml:apply>" if unit else value_xml


def definition_xml(name: str, expr: str, unit: str = "") -> str:
    """`name := expr` (a number or formula given as text), optionally multiplied by a unit."""
    value = _with_unit(formula_xml(parse(expr)), unit)
    return f"<ml:define>{_identifier_xml(name, contextual=False)}{value}</ml:define>"


def evaluation_xml(name: str, unit: str = "", override_xml: str = "") -> str:
    """`name =` showing the result: in `unit` if given, in the unit settings copied as `override_xml` from another
    worksheet if given, or otherwise in the result's own units."""
    override = override_xml or (unit_xml(unit) if unit else "<ml:placeholder />")
    return f"<ml:eval>{_identifier_xml(name)}<ml:unitOverride>{override}</ml:unitOverride></ml:eval>"


# ---------------------------------------------------------------- region XML
@dataclass(frozen=True)
class Box:
    """Where a text region sits and how big it is, in px."""

    left: float
    top: float
    width: float
    height: float


def _tag_attribute(tag: str | None) -> str:
    return f' tag="{tag}"' if tag else ""


def text_region_xml(region_id: int, relationship_id: str, style: str, box: Box, tag: str | None = None) -> str:
    """A text region. `relationship_id` points at the XamlPackage that holds the text itself."""
    font_size, colour = STYLES[style]
    return (
        f'<region region-id="{region_id}"{_tag_attribute(tag)} width="{box.width}" actualWidth="{box.width}" '
        f'actualHeight="{box.height:.4f}" top="{box.top:.4f}" left="{box.left}">'
        f'<text item-idref="{relationship_id}">'
        f'<FlowDocument FontFamily="Tahoma" FontStyle="Normal" FontWeight="Normal" FontSize="{font_size}" '
        f'Foreground="{colour}" Background="#00FFFFFF" TextAlignment="Left" xml:lang="en-us" '
        f'Typography.Variants="Normal" xmlns="{WPF_NS}" /></text></region>'
    )


def math_region_xml(region_id: int, result_id: int, body: str, *, top: float, left: float,
                    tag: str | None = None) -> str:
    """A math region. `result_id` is the slot in result.xml where Prime stores the calculated value."""
    return (
        f'<region region-id="{region_id}"{_tag_attribute(tag)} actualWidth="{MATH_REGION_WIDTH_HINT}" '
        f'actualHeight="{MATH_REGION_HEIGHT}" top="{top:.4f}" left="{left}">'
        f'<math resultRef="{result_id}">{body}</math></region>'
    )


# ---------------------------------------------------------------- package parts
def _document_xml(root: str, inner: str) -> str:
    namespaces = f'xmlns:ml="{ML_NS}" xmlns:u="{UNITS_NS}" xmlns="{WS_NS}"'
    extra = ' msg-id="NoMessage"' if root == "worksheet" else ""
    return f'{XML_DECLARATION}<{root}{extra} {namespaces}><regions>{inner}</regions></{root}>'


def integration_xml(designations: list[Designation]) -> str:
    """mathcad/integration.xml: which regions are designated inputs/outputs, with their aliases."""
    by_region: dict[int, tuple[IoKind, list[str]]] = {}
    for d in designations:
        by_region.setdefault(d.region_id, (d.kind, []))[1].append(d.alias)
    regions = "".join(
        f'<region region-id="{region_id}" ioTagType="{kind.value}"><{kind.value.lower()}Aliases>'
        + "".join(f"<alias>{escape(a)}</alias>" for a in aliases)
        + f"</{kind.value.lower()}Aliases></region>"
        for region_id, (kind, aliases) in by_region.items()
    )
    return f'{XML_DECLARATION}<regions xmlns="{INTEGRATION_NS}">{regions}</regions>'


def empty_results_xml(result_count: int) -> str:
    """mathcad/result.xml with no stored values. Prime reuses cached results if any exist, so leaving them
    out forces it to calculate everything when the worksheet is opened."""
    entries = "".join(f'<resultData result-id="{i}" />' for i in range(result_count))
    return (f'{XML_DECLARATION}<resultsList xmlns="{RESULT_NS}" xmlns:ml="{ML_NS}" xmlns:u="{UNITS_NS}">'
            f"{entries}</resultsList>")


def cached_worksheet_xml(regions: list[str]) -> str:
    """The cached copy of an included worksheet's definitions (mathcad/include/includeN.xml)."""
    return (
        f'{XML_DECLARATION}<cachedWorksheet xmlns:ml="{ML_NS}" xmlns:u="{UNITS_NS}" xmlns="{WS_NS}">'
        f'<regions>{"".join(regions)}</regions>'
        f'<calculation xmlns="{CALCULATION_NS}"><builtInVariables />'
        '<calculationBehavior exact-boolean="true" units-in-symbolics="true" constants-in-symbolics="true" '
        'symbolic-engine="axiom" /></calculation></cachedWorksheet>'
    )


def content_types_with_includes(skeleton_xml: str, include_parts: list[str]) -> str:
    """The skeleton's content types, minus its own include part, plus one entry per include we generated."""
    xml = re.sub(r'<Override PartName="/mathcad/include/[^"]*" ContentType="[^"]*" />', "", skeleton_xml)
    overrides = "".join(f'<Override PartName="{p}" ContentType="{CONTENT_TYPE_INCLUDE}" />' for p in include_parts)
    return xml.replace("</Types>", overrides + "</Types>")


# ---------------------------------------------------------------- sheet
@dataclass
class Sheet:
    """One worksheet under construction. Content is added in reading order; `y` tracks the free space below it."""

    regions: list[str] = field(default_factory=list)
    header_regions: list[str] = field(default_factory=list)
    footer_regions: list[str] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    header_relationships: list[Relationship] = field(default_factory=list)
    footer_relationships: list[Relationship] = field(default_factory=list)
    xaml_parts: dict[str, bytes] = field(default_factory=dict)  # part name -> text region package
    designations: list[Designation] = field(default_factory=list)
    tags: dict[str, int] = field(default_factory=dict)          # tag -> page number (1-based)
    definitions: list[str] = field(default_factory=list)        # math XML of each definition, for include caches
    includes: dict[str, bytes] = field(default_factory=dict)    # part name -> cached worksheet XML
    page: int = 0                                               # 0-based current page
    y: float = TOP_MARGIN                                       # top of free space on the current page
    _region_count: int = field(default=0, init=False, repr=False)
    _result_count: int = field(default=0, init=False, repr=False)
    _flow_count: int = field(default=0, init=False, repr=False)

    # -- ids (every region and every calculated result needs a worksheet-unique number)
    def next_region_id(self) -> int:
        self._region_count += 1
        return self._region_count - 1

    def next_result_id(self) -> int:
        self._result_count += 1
        return self._result_count - 1

    def _add_text_package(self, paragraphs: list[list[Run]], style: str, relationships: list[Relationship]) -> str:
        """Store the text and return the relationship id the region uses to refer to it."""
        part = f"FlowDocument{self._flow_count}.XamlPackage"
        self._flow_count += 1
        self.xaml_parts[f"mathcad/xaml/{part}"] = xaml_package(paragraphs, style)
        relationship = Relationship(new_relationship_id(), REL_FLOW_DOCUMENT, f"/mathcad/xaml/{part}")
        relationships.append(relationship)
        return relationship.id

    # -- page model
    @property
    def abs_y(self) -> float:
        """`y` measured from the top of the whole worksheet, which is how region positions are stored."""
        return self.page * (PAGE_CONTENT_HEIGHT + PAGE_BREAK_HEIGHT) + self.y

    def ensure_space(self, height: float) -> None:
        """Start a new page if `height` would not fit below the current position."""
        if self.y + height > PAGE_CONTENT_HEIGHT and self.y > TOP_MARGIN:
            self.page_break()

    def page_break(self) -> None:
        """End the current page. Prime stores a page break as a thin region at the bottom of the page."""
        top = self.page * (PAGE_CONTENT_HEIGHT + PAGE_BREAK_HEIGHT) + PAGE_CONTENT_HEIGHT
        region_id = self.next_region_id()
        self.regions.append(
            f'<region region-id="{region_id}" height="{PAGE_BREAK_HEIGHT}" actualWidth="{PAGE_WIDTH}" '
            f'actualHeight="{PAGE_BREAK_HEIGHT}" top="{top}" left="0"><pageBreak /></region>'
        )
        self.page += 1
        self.y = TOP_MARGIN

    def skip(self, px: float) -> None:
        self.y = snap(self.y + px)

    def _record_tag(self, tag: str | None) -> None:
        if tag:
            self.tags[tag] = self.page + 1

    # -- text
    def text(self, text: RichText, style: str = "Normal", *, tag: str | None = None, width: float = DEFAULT_TEXT_WIDTH,
             left: float = LEFT_MARGIN, advance: bool = True) -> int:
        """Add text at the current position. `advance=False` leaves the position unchanged so that something
        else (a math region) can be placed on the same row. Returns the region id."""
        paragraphs = as_paragraphs(text)
        height = text_height(paragraphs, style, width)
        region_id = self.next_region_id()
        relationship_id = self._add_text_package(paragraphs, style, self.relationships)
        self.ensure_space(height)
        self._record_tag(tag)
        box = Box(left=left, top=self.abs_y, width=width, height=height)
        self.regions.append(text_region_xml(region_id, relationship_id, style, box, tag))
        if advance:
            self.y = snap(self.y + height + GRID)
        return region_id

    def text_at(self, text: RichText, regions: list[str], *, top: float, left: float, width: float,
                style: str = "Normal") -> int:
        """Add text at an explicit position inside `regions` (an area's region list)."""
        paragraphs = as_paragraphs(text)
        region_id = self.next_region_id()
        relationship_id = self._add_text_package(paragraphs, style, self.relationships)
        box = Box(left=left, top=top, width=width, height=text_height(paragraphs, style, width))
        regions.append(text_region_xml(region_id, relationship_id, style, box))
        return region_id

    def header_text(self, text: str, width: float = 500) -> None:
        self._furniture_text(text, width, self.header_regions, self.header_relationships)

    def footer_text(self, text: str, width: float = 300) -> None:
        self._furniture_text(text, width, self.footer_regions, self.footer_relationships)

    def _furniture_text(self, text: str, width: float, regions: list[str], relationships: list[Relationship]) -> None:
        paragraphs = as_paragraphs(text)
        region_id = self.next_region_id()
        relationship_id = self._add_text_package(paragraphs, "Normal", relationships)
        box = Box(left=LEFT_MARGIN, top=HEADER_TOP, width=width, height=text_height(paragraphs, "Normal", width))
        regions.append(text_region_xml(region_id, relationship_id, "Normal", box))

    # -- math
    def record_definition(self, body: str) -> None:
        """Remember a definition so that worksheets including this one can carry a cached copy of it."""
        self.definitions.append(body)

    def _math_in_flow(self, body: str, left: float, tag: str | None) -> int:
        region_id = self.next_region_id()
        self.ensure_space(MATH_REGION_HEIGHT)
        self._record_tag(tag)
        self.regions.append(math_region_xml(region_id, self.next_result_id(), body, top=self.abs_y, left=left, tag=tag))
        self.y = snap(self.y + MATH_REGION_HEIGHT + GRID)
        return region_id

    def define(self, name: str, expr: str, unit: str = "", *, left: float = LEFT_MARGIN, tag: str | None = None) -> int:
        """Add `name := expr [unit]` at the current position."""
        body = definition_xml(name, expr, unit)
        self.record_definition(body)
        return self._math_in_flow(body, left, tag)

    def evaluate(self, name: str, unit: str = "", *, left: float = LEFT_MARGIN, tag: str | None = None,
                 override_xml: str = "") -> int:
        """Add `name =` (shows the result) at the current position."""
        return self._math_in_flow(evaluation_xml(name, unit, override_xml), left, tag)

    # -- areas
    def area_from_frame(self, tag: str, frame: Frame) -> None:
        """Wrap everything placed in `frame` in a tagged Area at the current position. An Area cannot be split
        across pages, so the whole thing moves to the next page if it does not fit."""
        height = snap(frame.y + AREA_PADDING)
        self.ensure_space(height)
        region_id = self.next_region_id()
        self._record_tag(tag)
        self.regions.append(
            f'<region region-id="{region_id}" tag="{tag}" height="{height}" width="{AREA_WIDTH}" '
            f'actualWidth="{AREA_WIDTH}" actualHeight="{height}" top="{self.abs_y:.4f}" left="0">'
            f'<Area AreaHeight="{height}"><regions>{"".join(frame.regions)}</regions></Area></region>'
        )
        self.y = snap(self.y + height + GRID)

    # -- includes
    def include(self, href: str, source: Sheet | None = None) -> None:
        """Include another worksheet (its definitions become available below this point).

        Prime refuses to open a worksheet with an include whose reference has no last-saved-date, so that is
        always written.

        With `source`, a cached copy of that sheet's definitions is stored in the package too. Prime then uses the
        cache and does not re-read the file when this worksheet is opened (the include's refresh button does).
        Without `source` there is no cache, so Prime reads the live file on open - which is what a worksheet written
        by hand needs, since its definitions are not known here.
        """
        region_id = self.next_region_id()
        self.ensure_space(INCLUDE_REGION_HEIGHT)
        item_reference = ""
        if source is not None:
            part = f"/mathcad/include/include{region_id}.xml"
            cached = [
                f'<region region-id="{i}" actualWidth="0" actualHeight="0" top="{CACHED_ROW_SPACING * (i + 1):.1f}" '
                f'left="{LEFT_MARGIN}"><math resultRef="{self.next_result_id()}">{body}</math></region>'
                for i, body in enumerate(source.definitions)
            ]
            self.includes[part] = cached_worksheet_xml(cached).encode("utf-8")
            relationship = Relationship(new_relationship_id(), REL_INCLUDE, part)
            self.relationships.append(relationship)
            item_reference = f' item-idref="{relationship.id}"'
        self.regions.append(
            f'<region region-id="{region_id}" width="{AREA_WIDTH}" actualWidth="{AREA_WIDTH}" '
            f'actualHeight="{INCLUDE_REGION_HEIGHT}" top="{self.abs_y:.4f}" left="0">'
            f'<reference href={quoteattr(href)} last-saved-date="{datetime.now():%m/%d/%Y %H:%M:%S}"'
            f'{item_reference} /></region>'
        )
        self.y = snap(self.y + INCLUDE_REGION_HEIGHT + GRID)

    # -- designations
    def designate(self, region_id: int, kind: IoKind, alias: str) -> None:
        """Expose a region to other programs as a named input or output."""
        self.designations.append(Designation(region_id, kind, alias))

    # -- writing
    def package_parts(self) -> dict[str, bytes]:
        """Every part of the .mcdx package, by part name."""
        with zipfile.ZipFile(SKELETON) as skeleton:
            parts = {name: skeleton.read(name) for name in SKELETON_PARTS}
        content_types = content_types_with_includes(parts[CONTENT_TYPES_PART].decode("utf-8-sig"), list(self.includes))
        parts[CONTENT_TYPES_PART] = content_types.encode("utf-8")

        parts.update({
            "mathcad/worksheet.xml": _document_xml("worksheet", "".join(self.regions)).encode("utf-8"),
            "mathcad/header.xml": _document_xml("header", "".join(self.header_regions)).encode("utf-8"),
            "mathcad/footer.xml": _document_xml("footer", "".join(self.footer_regions)).encode("utf-8"),
            "mathcad/integration.xml": integration_xml(self.designations).encode("utf-8"),
            "mathcad/result.xml": empty_results_xml(self._result_count).encode("utf-8"),
            "mathcad/_rels/worksheet.xml.rels": relationships_xml(self.relationships).encode("utf-8"),
            "mathcad/_rels/header.xml.rels": relationships_xml(self.header_relationships).encode("utf-8"),
            "mathcad/_rels/footer.xml.rels": relationships_xml(self.footer_relationships).encode("utf-8"),
            **self.xaml_parts,
            **{name.lstrip("/"): data for name, data in self.includes.items()},
        })
        return parts

    def save(self, path: Path) -> None:
        write_package(path, self.package_parts())


class Frame:
    """The inside of an Area: regions positioned relative to the Area's top-left corner.

    Place things with `top`/`left`, track the next free row in `y`, then hand the frame to `Sheet.area_from_frame`.
    """

    def __init__(self, sheet: Sheet):
        self.sheet = sheet
        self.regions: list[str] = []
        self.y = TOP_MARGIN

    def _math(self, body: str, top: float, left: float) -> int:
        region_id = self.sheet.next_region_id()
        self.regions.append(math_region_xml(region_id, self.sheet.next_result_id(), body, top=top, left=left))
        return region_id

    def define(self, name: str, expr: str, unit: str = "", *, top: float, left: float = LEFT_MARGIN) -> int:
        body = definition_xml(name, expr, unit)
        self.sheet.record_definition(body)
        return self._math(body, top, left)

    def evaluate(self, name: str, unit: str = "", *, top: float, left: float) -> int:
        return self._math(evaluation_xml(name, unit), top, left)

    def text(self, text: RichText, *, top: float, left: float, width: float, style: str = "Normal") -> int:
        return self.sheet.text_at(text, self.regions, top=top, left=left, width=width, style=style)
