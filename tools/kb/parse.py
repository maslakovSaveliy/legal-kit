"""Parsing of requirement cards: frontmatter subset of YAML and level-2 sections."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):(.*)$")


@dataclass
class Card:
    """One requirement card.

    ``fm`` holds parsed frontmatter values, ``sections`` maps level-2 headings to their text.
    ``head`` is the text before the first section (title and intro quote) and ``fm_raw`` keeps
    every frontmatter entry verbatim, so that an emitted card can reuse the original formatting.
    """

    slug: str
    fm: dict
    sections: dict
    head: str = ""
    fm_raw: dict = field(default_factory=dict)


def _split_frontmatter(text: str):
    """Return (frontmatter_lines, body) or (None, text) when the text has no frontmatter."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return lines[1:index], "\n".join(lines[index + 1:])
    return None, text


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return re.sub(r'\\(["\\])', r"\1", value[1:-1])
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _split_inline_list(inner: str) -> list:
    """Split ``a, "b, c", d`` on commas that are outside quotes."""
    items, current, quote, escaped = [], [], None, False
    for char in inner:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return [_unquote(item) for item in items if item.strip()]


def _parse_value(first: str, continuation: list):
    value = first.strip()
    if value == "":
        items = []
        for line in continuation:
            match = re.match(r"^\s*-\s+(.*)$", line)
            if match:
                items.append(_unquote(match.group(1)))
        return items
    if value.startswith("[") and value.endswith("]"):
        return _split_inline_list(value[1:-1])
    return _unquote(value)


def _frontmatter_entries(lines: list):
    """Group frontmatter lines into (key, first_value_text, continuation_lines, raw_text)."""
    entries = []
    for line in lines:
        match = _KEY_RE.match(line)
        if match and not line[:1].isspace():
            entries.append([match.group(1), match.group(2), [], [line]])
        elif entries and line.strip():
            entries[-1][2].append(line)
            entries[-1][3].append(line)
    return [(key, first, cont, "\n".join(raw)) for key, first, cont, raw in entries]


def header_bytes(path) -> bytes:
    """Bytes of the frontmatter block of a file, closing ``---`` line included; empty if there is none."""
    lines = Path(path).read_bytes().split(b"\n")
    if lines and lines[0].startswith(b"\xef\xbb\xbf"):
        lines[0] = lines[0][3:]
    if not lines or lines[0].rstrip() != b"---":
        return b""
    for index in range(1, len(lines)):
        if lines[index].rstrip() == b"---":
            return b"\n".join(lines[: index + 1]) + b"\n"
    return b""


def read_text(path) -> str:
    """Read a UTF-8 file, dropping a byte order mark."""
    return Path(path).read_text(encoding="utf-8-sig")


def parse_frontmatter(text: str):
    """Return ``(frontmatter_dict, body)``; a text without frontmatter gives ``({}, text)``."""
    lines, body = _split_frontmatter(text)
    if lines is None:
        return {}, text
    fm = {key: _parse_value(first, cont) for key, first, cont, _ in _frontmatter_entries(lines)}
    return fm, body


def split_body(body: str, level: int = 2):
    """Split a markdown body into ``(preamble, {heading: text})`` at headings of the given level.

    Heading-like lines inside fenced code blocks are ignored. Section text is stripped of
    surrounding blank lines; repeated headings are concatenated.
    """
    heading = re.compile(rf"^#{{{level}}}(?!#)[ \t]+(.+?)[ \t]*$")
    preamble, sections = [], {}
    current = None
    fence = None
    for line in body.split("\n"):
        fence_match = _FENCE_RE.match(line)
        if fence is None and fence_match:
            fence = fence_match.group(1)
        elif fence is not None and fence_match and line.strip() == fence_match.group(1) \
                and fence_match.group(1)[0] == fence[0] and len(fence_match.group(1)) >= len(fence):
            fence = None
        elif fence is None:
            found = heading.match(line)
            if found:
                current = found.group(1).strip()
                sections.setdefault(current, [])
                if sections[current]:
                    sections[current].append("")
                continue
        (preamble if current is None else sections[current]).append(line)
    return (
        "\n".join(preamble).strip("\n"),
        {title: "\n".join(lines).strip("\n") for title, lines in sections.items()},
    )


def split_sections(body: str, level: int = 2) -> dict:
    """Return ``{heading: text}`` for headings of the given level, skipping fenced code blocks."""
    return split_body(body, level)[1]


def load_card(path) -> Card:
    """Read a card file; the slug is the file name without extension."""
    path = Path(path)
    text = read_text(path)
    lines, body = _split_frontmatter(text)
    fm, fm_raw = {}, {}
    if lines is not None:
        for key, first, cont, raw in _frontmatter_entries(lines):
            fm[key] = _parse_value(first, cont)
            fm_raw[key] = raw
    else:
        body = text
    head, sections = split_body(body)
    return Card(slug=path.stem, fm=fm, sections=sections, head=head, fm_raw=fm_raw)
