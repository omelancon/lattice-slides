"""Attribute blocks: ``{#id .class key=value key="quoted value"}`` (spec section 3.4)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

IDENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_TOKEN_RE = re.compile(
    r"""\s*(?:
        \#(?P<id>[^\s{}"']+)
      | \.(?P<cls>[^\s{}"'=]+)
      | (?P<key>[A-Za-z_][A-Za-z0-9_-]*)=(?:
            "(?P<dq>(?:[^"\\]|\\.)*)"
          | '(?P<sq>(?:[^'\\]|\\.)*)'
          | (?P<bare>[^\s{}"']+)
        )
    )""",
    re.X,
)
_CLASS_RE = re.compile(r"[A-Za-z_-][A-Za-z0-9_-]*\Z")
_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
# A trailing attribute block, not preceded by a backslash.
_TRAILING_RE = re.compile(r"(?:^|(?<=[^\\]))(\{[^{}]*\})\s*\Z")


class AttrError(ValueError):
    pass


@dataclass
class Attrs:
    id: str | None = None
    classes: list[str] = field(default_factory=list)
    kv: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default=None):
        return self.kv.get(key, default)

    def is_empty(self) -> bool:
        return self.id is None and not self.classes and not self.kv


def parse_attr_block(text: str) -> Attrs:
    """Parse ``{...}`` (braces included) into :class:`Attrs`. Raises AttrError."""
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        raise AttrError(f"attribute block must be enclosed in braces: {text!r}")
    inner = text[1:-1]
    attrs = Attrs()
    pos = 0
    while pos < len(inner):
        if inner[pos:].strip() == "":
            break
        m = _TOKEN_RE.match(inner, pos)
        if not m or m.end() == pos:
            raise AttrError(f"cannot parse attributes near {inner[pos:].strip()!r}")
        if m.group("id") is not None:
            if attrs.id is not None:
                raise AttrError("more than one #id in attribute block")
            if not IDENT_RE.match(m.group("id")):
                raise AttrError(f"invalid id {m.group('id')!r}")
            attrs.id = m.group("id")
        elif m.group("cls") is not None:
            if not _CLASS_RE.match(m.group("cls")):
                raise AttrError(f"invalid class {m.group('cls')!r}")
            attrs.classes.append(m.group("cls"))
        else:
            key = m.group("key")
            if key in attrs.kv:
                raise AttrError(f"attribute {key!r} given twice")
            if m.group("dq") is not None:
                val = re.sub(r"\\(.)", r"\1", m.group("dq"))
            elif m.group("sq") is not None:
                val = re.sub(r"\\(.)", r"\1", m.group("sq"))
            else:
                val = m.group("bare")
            attrs.kv[key] = val
        pos = m.end()
    return attrs


def split_trailing_attrs(text: str) -> tuple[str, str | None]:
    """Split ``"Title {#id}"`` into ``("Title", "{#id}")``."""
    m = _TRAILING_RE.search(text)
    if not m:
        return text, None
    return text[: m.start(1)].rstrip(), m.group(1)


def split_name_and_attrs(info: str) -> tuple[str, str | None]:
    """Split a fence or container info string ``"name {attrs}"``."""
    info = info.strip()
    if not info:
        return "", None
    m = re.match(r"([^\s{]+)\s*(\{.*\})?\s*\Z", info, re.S)
    if not m:
        name, _, rest = info.partition(" ")
        return name, rest.strip() or None
    return m.group(1), m.group(2)


def to_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    v = value.strip().lower()
    if v in ("true", "yes", "1", "on"):
        return True
    if v in ("false", "no", "0", "off"):
        return False
    raise AttrError(f"expected a boolean, got {value!r}")
