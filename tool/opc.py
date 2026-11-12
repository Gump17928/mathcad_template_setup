"""Generic Open Packaging Convention helpers (zip parts + relationships). Nothing here knows about Mathcad."""
from __future__ import annotations

import io
import secrets
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

XML_DECLARATION = '<?xml version="1.0" encoding="utf-8"?>'
RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CONTENT_TYPES_PART = "[Content_Types].xml"


@dataclass(frozen=True)
class Relationship:
    id: str
    type: str
    target: str  # absolute part name, e.g. /mathcad/xaml/FlowDocument0.XamlPackage


def new_relationship_id() -> str:
    """Ids only need to be unique inside one .rels file; Prime itself uses 'R' plus 16 hex digits."""
    return "R" + secrets.token_hex(8)


def relationships_xml(relationships: Iterable[Relationship]) -> str:
    body = "".join(f'<Relationship Type="{r.type}" Target="{r.target}" Id="{r.id}" />' for r in relationships)
    return f'{XML_DECLARATION}<Relationships xmlns="{RELATIONSHIPS_NS}">{body}</Relationships>'


def package_bytes(parts: dict[str, bytes]) -> bytes:
    """Zip the parts. The content-types part goes first, as the packaging convention expects."""
    names = list(parts)
    if CONTENT_TYPES_PART in names:
        names.remove(CONTENT_TYPES_PART)
        names.insert(0, CONTENT_TYPES_PART)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, parts[name])
    return buffer.getvalue()


def write_package(path: Path, parts: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(package_bytes(parts))
