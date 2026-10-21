"""Dates from the legal-basis table of a card."""

from __future__ import annotations

import re
from datetime import date

from .links import plain_text

_FROM_DATE = re.compile(r"(?<![А-Яа-яЁёA-Za-z])[сС]\s+\*{0,2}(\d{2})\.(\d{2})\.(\d{4})")
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")


def split_cells(line: str) -> list:
    """Split a markdown table row into cells; pipes inside ``[[a|b]]`` and ``\\|`` do not split."""
    text = line.strip()
    text = re.sub(r"\[\[[^\]]*\]\]", lambda m: m.group(0).replace("|", "\x00"), text)
    text = text.replace("\\|", "\x01")
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.replace("\x00", "|").replace("\x01", "|").strip() for cell in text.split("|")]


def iter_tables(md: str):
    """Yield ``(header_cells, [row_cells, ...])`` for every pipe table in the text."""
    block = []
    for line in md.split("\n") + [""]:
        if line.lstrip().startswith("|"):
            block.append(line)
            continue
        if len(block) >= 2:
            header = split_cells(block[0])
            if all(_SEPARATOR_CELL.match(cell) for cell in split_cells(block[1])):
                yield header, [split_cells(row) for row in block[2:]]
        block = []


def _from_date(cell: str):
    """Latest ISO date introduced by the word «с» in a cell, or None."""
    found = []
    for day, month, year in _FROM_DATE.findall(cell):
        try:
            found.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return max(found).isoformat() if found else None


def norm_dates(section_md: str) -> list:
    """Return ``[{"norm", "from"}]`` for the rows of the «… | Редакция …» table.

    ``from`` is the latest date written as «с DD.MM.YYYY» (also in bold) converted to ISO, so a
    norm with a later amendment carries the amendment date. Text such as «дата не указана»,
    an empty cell or a date that is not introduced by «с» gives ``None``.
    """
    result, seen = [], set()
    for header, rows in iter_tables(section_md):
        if not header or not header[-1].lower().startswith("редакция"):
            continue
        for cells in rows:
            norm = plain_text(cells[0]) if cells else ""
            if not norm:
                continue
            entry = (norm, _from_date(cells[-1]) if len(cells) > 1 else None)
            if entry not in seen:
                seen.add(entry)
                result.append({"norm": entry[0], "from": entry[1]})
    return result
