"""Text for worksheet regions: styled runs with optional links, WPF XAML packages, and a height estimate."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple
from xml.sax.saxutils import escape, quoteattr

from opc import (
    CONTENT_TYPES_NS,
    CONTENT_TYPES_PART,
    RELATIONSHIPS_NS,
    XML_DECLARATION,
    new_relationship_id,
    package_bytes,
)

WPF_NS = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"
FONT_FAMILY = "Tahoma"  # the family of Prime's default styles

# Rough Tahoma metrics used only to estimate how tall a text region will be. Prime wraps and measures text itself,
# so these only drive this tool's own page layout.
AVERAGE_CHAR_WIDTH = 0.55  # of the font size
LINE_HEIGHT = 1.21         # of the font size

LINK_COLOUR = "#FF0000FF"


class TextStyle(NamedTuple):
    font_size: float  # px
    colour: str       # ARGB


# Prime's built-in text styles; the names must match the worksheet's presentation settings.
STYLES: dict[str, TextStyle] = {
    "Title": TextStyle(37.3333333333333, "#FF000000"),
    "Subtitle": TextStyle(24.0, "#FF000000"),
    "Heading 1": TextStyle(21.3333333333333, "#FF2E3192"),
    "Heading 2": TextStyle(17.3333333333333, "#FF2E3192"),
    "Heading 3": TextStyle(16.0, "#FF2E3192"),
    "Normal": TextStyle(14.6666666666667, "#FF000000"),
}


@dataclass
class Run:
    text: str
    link: str | None = None  # "#tag" for this worksheet, or "file.mcdx#tag" for another one


# Accepted wherever text is given:
#   "plain"  |  Run(...)  |  [run, run, ...] (one paragraph)  |  [[...], [...]] (several paragraphs)
RichText = str | Run | list


def as_paragraphs(text: RichText) -> list[list[Run]]:
    """Normalise any accepted text form to a list of paragraphs, each a list of Runs."""
    if isinstance(text, (str, Run)) or (text and not isinstance(text[0], list)):
        text = [text]
    paragraphs = []
    for paragraph in text:
        items = paragraph if isinstance(paragraph, list) else [paragraph]
        paragraphs.append([Run(item) if isinstance(item, str) else item for item in items])
    return paragraphs


def text_height(text: RichText, style: str, width: float) -> float:
    """Estimated height in px of `text` wrapped to `width`."""
    size = STYLES[style].font_size
    lines = 0
    for paragraph in as_paragraphs(text):
        characters = sum(len(run.text) for run in paragraph)
        lines += max(1, math.ceil(characters * size * AVERAGE_CHAR_WIDTH / width))
    return lines * size * LINE_HEIGHT


def xaml_package(paragraphs: list[list[Run]], style: str) -> bytes:
    """The .XamlPackage part holding one text region's content. Headings are simply runs in a heading style."""
    font_size, colour = STYLES[style]
    out = [
        f'<Section xmlns="{WPF_NS}" xml:space="preserve" TextAlignment="Left" xml:lang="en-us" '
        f'FontFamily="{FONT_FAMILY}" FontStyle="Normal" FontWeight="Normal" FontSize="{font_size}" '
        f'Foreground="{colour}">'
    ]
    for paragraph in paragraphs:
        out.append("<Paragraph>")
        for run in paragraph:
            xml = f"<Run style={quoteattr(style)}>{escape(run.text)}</Run>"
            if run.link:
                xml = (
                    f'<Hyperlink Foreground="{LINK_COLOUR}" NavigateUri={quoteattr(run.link)} '
                    f'TextDecorations="Underline">{xml}</Hyperlink>'
                )
            out.append(xml)
        out.append("</Paragraph>")
    out.append("</Section>")

    content_types = (
        f'{XML_DECLARATION}<Types xmlns="{CONTENT_TYPES_NS}">'
        '<Default Extension="xaml" ContentType="application/vnd.ms-wpf.xaml+xml" />'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" /></Types>'
    )
    rels = (
        f'{XML_DECLARATION}<Relationships xmlns="{RELATIONSHIPS_NS}">'
        '<Relationship Type="http://schemas.microsoft.com/wpf/2005/10/xaml/entry" '
        f'Target="/Xaml/Document.xaml" Id="{new_relationship_id()}" /></Relationships>'
    )
    return package_bytes({
        CONTENT_TYPES_PART: content_types.encode("utf-8"),
        "_rels/.rels": rels.encode("utf-8"),
        "Xaml/Document.xaml": "".join(out).encode("utf-8"),
    })
