"""Document templates of the knowledge base: sanitized text files and JSON indexes.

A template (``wiki/references/shablon-*.md``) has numbered sections: 1 purpose, 2 required content
(tables of elements), 3 template text (blocks in ```markdown fences), 4 placement, 5 what to fill
in (table of placeholders), 6 disputed points, 7 See Also, 8 Sources.

The pack gets, per template, ``templates/<t>/text.md`` (sections 3 and 4) and
``templates/<t>/meta.md`` (sections 1, 5 and 6), and three indexes for all templates:
``elements.json`` (section 2), ``placeholders.json`` (section 5 plus every placeholder met in the
shipped text) and ``forbidden-clauses.json`` (tables whose header starts with «Формулировка»).
Sections 7 and 8 are dropped. Fenced blocks are the text of the future document: they are copied
byte for byte, links and process markers are rewritten outside of them only.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .links import LinkCtx, sanitize, unlink
from .parse import load_card
from .prose import scrub

TEMPLATE_PREFIX = "shablon-"
TEXT_SECTIONS = (3, 4)
META_SECTIONS = (1, 5, 6)
ELEMENTS_SECTION = 2
PLACEHOLDER_SECTION = 5
PLACEHOLDER_SOURCES = (1, 3, 4, 5, 6)  # every shipped section; the placeholders index must cover all of them
META_FRONTMATTER = ("summary", "updated", "verified", "confidence", "volatility")
TOC_MIN_LINES = 100

ELEMENT_HEADER = ["Элемент", "Статус", "Норма", "Карточка"]
PLACEHOLDER_HEADER = ["Плейсхолдер", "Что вписать"]
FORBIDDEN_HEADER_START = "Формулировка"
STATUSES = ("обязательно", "при условии", "рекомендуется")
SECTION_LETTERS = "АБВГДЕЖЗИЙК"
METHODS = ("norm", "practice", "interpretation", "inference", "platform")

TEXT_FILE = "text.md"
META_FILE = "meta.md"
INDEX_FILES = ("elements.json", "placeholders.json", "forbidden-clauses.json", "templates/README.md")

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_WIKILINK = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_ELEMENT_ID = re.compile(r"^([А-К])(\d+)\.\s+(.+)$", re.S)
_STATUS = re.compile(r"^(" + "|".join(STATUSES) + r")(?![\w])(.*)$", re.S)
_PLACEHOLDER = re.compile(r"\{\{([A-ZА-ЯЁ0-9_]+)\}\}")
_HEADING = re.compile(r"^(#{2,3})[ \t]+(.+?)[ \t]*$")
_SECTION_NUMBER = re.compile(r"^(\d+)\.\s")
_DASH_ONLY = {"—", "–", "-"}
_AGENCIES = (
    r"фнс|ркн|роскомнадзор\w*|фас|цб|банк\w* росси\w*|роспотребнадзор\w*|минцифр\w*|минфин\w*|минкомсвяз\w*"
    r"|минпромторг\w*|мвд|фсб|фстэк|роструд\w*|орган\w*|ведомств\w*"
)
_RISK = re.compile(r"зон\w* риска", re.I)
_PLATFORM = re.compile(r"правил\w* (?:магазин\w*|стор\w*|площадок)|\bне закон\b")
_INTERPRETATION = re.compile(r"не норм\w*|ориентир\w* толковани\w*|ориентиры\b|\bfaq\b")
_POSITION = re.compile(
    rf"позици\w*\W+(?:\w+\W+){{0,4}}?(?:{_AGENCIES})\b|\b(?:{_AGENCIES})\W+(?:\w+\W+){{0,4}}?позици\w*"
)


class TemplateError(ValueError):
    """A template does not have the structure the generator relies on."""


@dataclass
class Template:
    """One template: ``slug`` is the file stem without ``shablon-``, ``sections`` maps level-2 headings to text."""

    slug: str
    fm: dict
    sections: dict
    head: str = ""
    fm_raw: dict = field(default_factory=dict)

    def section(self, number: int):
        """``(heading, text)`` of the section whose heading starts with ``<number>.``; ``None`` if absent."""
        for heading, text in self.sections.items():
            found = _SECTION_NUMBER.match(heading)
            if found and int(found.group(1)) == number:
                return heading, text
        return None

    def section_text(self, number: int) -> str:
        found = self.section(number)
        return found[1] if found else ""


@dataclass
class Table:
    header: list
    rows: list


def load_template(path) -> Template:
    """Read ``shablon-<name>.md``; the slug is ``<name>``."""
    card = load_card(path)
    slug = card.slug[len(TEMPLATE_PREFIX):] if card.slug.startswith(TEMPLATE_PREFIX) else card.slug
    return Template(slug=slug, fm=card.fm, sections=card.sections, head=card.head, fm_raw=card.fm_raw)


def load_templates(topic) -> list:
    """All templates of the knowledge base, sorted by slug."""
    folder = Path(topic) / "wiki" / "references"
    templates = [load_template(path) for path in sorted(folder.glob(TEMPLATE_PREFIX + "*.md"))]
    return sorted(templates, key=lambda t: t.slug)


# ------------------------------------------------------------------ fences and tables


def _closes(line: str, fence: str) -> bool:
    """True when ``line`` closes a block opened with the marker ``fence``."""
    match = _FENCE.match(line)
    return bool(match) and line.strip() == match.group(1) and match.group(1)[0] == fence[0] \
        and len(match.group(1)) >= len(fence)


def segments(md: str) -> list:
    """Split markdown into ``[(fenced, text)]``; a fenced segment holds its marker lines too.

    Joining the texts with newlines gives the input back. A fence left open runs to the end.
    """
    result, buf, fence = [], [], None

    def flush(fenced: bool):
        if buf:
            result.append((fenced, "\n".join(buf)))
            buf.clear()

    for line in md.split("\n"):
        if fence is None:
            match = _FENCE.match(line)
            if match:
                flush(False)
                fence = match.group(1)
            buf.append(line)
        else:
            buf.append(line)
            if _closes(line, fence):
                flush(True)
                fence = None
    flush(fence is not None)
    return result


def fenced_blocks(md: str) -> list:
    """``[(info, body)]`` of every fenced block; ``info`` is the text after the opening marker."""
    blocks = []
    for fenced, text in segments(md):
        if fenced:
            lines = text.split("\n")
            opening = _FENCE.match(lines[0])
            closed = len(lines) > 1 and _closes(lines[-1], opening.group(1))
            blocks.append((opening.group(2).strip(), "\n".join(lines[1:-1] if closed else lines[1:])))
    return blocks


def split_row(line: str) -> list:
    """Cells of a table row. ``[[a|b]]`` keeps its bar, ``\\|`` is an escaped bar."""
    text = line.strip()
    text = text[1:] if text.startswith("|") else text
    cells, current, index = [], [], 0
    while index < len(text):
        if text.startswith("[[", index) and (end := text.find("]]", index)) != -1:
            current.append(text[index:end + 2])
            index = end + 2
        elif text.startswith("\\|", index):
            current.append("|")
            index += 2
        elif text[index] == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
        else:
            current.append(text[index])
            index += 1
    tail = "".join(current).strip()
    if tail:
        cells.append(tail)
    return cells


def tables(md: str) -> list:
    """Tables outside fenced blocks, in order. A row of another width than the header is an error."""
    found = []
    for fenced, text in segments(md):
        if fenced:
            continue
        lines = text.split("\n")
        index = 0
        while index < len(lines):
            if lines[index].lstrip().startswith("|") and index + 1 < len(lines) and _SEPARATOR.match(lines[index + 1]):
                header = split_row(lines[index])
                rows, index = [], index + 2
                while index < len(lines) and lines[index].lstrip().startswith("|"):
                    row = split_row(lines[index])
                    if len(row) != len(header):
                        raise TemplateError(f"table row has {len(row)} cells, header has {len(header)}: {lines[index][:80]}")
                    rows.append(row)
                    index += 1
                found.append(Table(header, rows))
            else:
                index += 1
    return found


def element_tables(t: Template) -> list:
    """Tables of section 2 with the header ``Элемент | Статус | Норма | Карточка``."""
    return [table for table in tables(t.section_text(ELEMENTS_SECTION)) if table.header == ELEMENT_HEADER]


# ------------------------------------------------------------------ cell text


def plain(cell: str) -> str:
    """Single-line text of a cell: links reduced to text, process markers reworded, no dash-only values."""
    text = re.sub(r"\s+", " ", scrub(unlink(cell))).strip()
    return "" if text in _DASH_ONLY else text


def _outer_parens(text: str) -> bool:
    """True when the first ``(`` of ``text`` closes at its last character."""
    if not (text.startswith("(") and text.endswith(")")):
        return False
    depth = 0
    for index, char in enumerate(text):
        depth += (char == "(") - (char == ")")
        if depth == 0:
            return index == len(text) - 1
    return False


def split_status(cell: str):
    """``(status, qualifier)``: the leading status word and what follows it, without ``:`` or outer parentheses."""
    found = _STATUS.match(cell.strip())
    if not found:
        raise TemplateError(f"unknown status: {cell[:60]!r}")
    rest = found.group(2).strip().lstrip(":.").strip()
    if _outer_parens(rest):
        rest = rest[1:-1].strip()
    return found.group(1), rest


def method_of(text: str, qualifier: str, norm: str) -> str:
    """What the element rests on; the first rule that fits wins.

    1. ``platform``: «правила магазина / стора / площадок» or «не закон» anywhere in the row.
    2. ``interpretation``: «трактовк…» anywhere in the row; or, in the element text or the status
       qualifier, «не норма», «ориентир толкования», «ориентиры», «FAQ» or a «позиция» next to an
       agency («ФНС», «РКН», «ФАС», «Роспотребнадзор», «орган» …).
    3. ``practice``: «практик…» in the qualifier or «инженерная практика» anywhere in the row.
    4. ``inference``: the whole word «вывод» anywhere in the row.
    5. An empty «Норма» cell (or a dash) cannot be a norm: ``practice``.
    6. Otherwise ``norm``.

    The status says that the document must contain the element, the method says what its legal
    basis is, so a «обязательно» element can have a method other than ``norm``. The «Норма» cell is
    not searched for the markers of rule 2 except «трактовк…»: there they often label a side source
    (a review of the Supreme Court next to the statute), not the element.
    """
    own = f"{text} {qualifier}".lower()
    row = f"{own} {norm}".lower()
    if _PLATFORM.search(row):
        return "platform"
    if "трактовк" in row or _INTERPRETATION.search(own) or _POSITION.search(own):
        return "interpretation"
    if "практик" in qualifier.lower() or "инженерная практика" in row:
        return "practice"
    if re.search(r"\bвывод\b", row):
        return "inference"
    return "norm" if norm.strip() else "practice"


# ------------------------------------------------------------------ indexes


def _element(slug: str, row: list) -> dict:
    found = _ELEMENT_ID.match(plain(row[0]))
    if not found:
        raise TemplateError(f"{slug}: element without id: {row[0][:60]!r}")
    letter, number, text = found.groups()
    status, qualifier = split_status(plain(row[1]))
    norm = plain(row[2])
    requirements = []
    for card in _WIKILINK.findall(row[3]):
        if not card.startswith(TEMPLATE_PREFIX) and f"ru:{card.strip()}" not in requirements:
            requirements.append(f"ru:{card.strip()}")
    return {
        "template": slug,
        "id": f"{letter}{number}",
        "section": letter,
        "text": text,
        "status": status,
        "qualifier": qualifier,
        "method": method_of(text, qualifier, norm),
        "norm": norm,
        "requirements": requirements,
    }


def _element_order(row: dict):
    return (SECTION_LETTERS.index(row["section"]), int(row["id"][1:]))


def extract_elements(t: Template) -> list:
    """Rows of ``elements.json`` for one template, sorted by section letter and number."""
    rows = [_element(t.slug, cells) for table in element_tables(t) for cells in table.rows]
    ids = [row["id"] for row in rows]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise TemplateError(f"{t.slug}: repeated element ids: {', '.join(duplicates)}")
    return sorted(rows, key=_element_order)


def extract_placeholders(t: Template) -> dict:
    """``{name: {"hint": str, "templates": [slug]}}`` for one template.

    The hint is the «Что вписать» cell of the section 5 row that lists the name (the first
    non-empty one). A placeholder met in the shipped text but not listed there has an empty hint.
    """
    found = {}
    for number in PLACEHOLDER_SOURCES:
        for name in _PLACEHOLDER.findall(t.section_text(number)):
            found.setdefault(name, {"hint": "", "templates": [t.slug]})
    for table in tables(t.section_text(PLACEHOLDER_SECTION)):
        if table.header != PLACEHOLDER_HEADER:
            continue
        for names_cell, hint_cell in table.rows:
            hint = plain(hint_cell)
            for name in _PLACEHOLDER.findall(names_cell):
                entry = found.setdefault(name, {"hint": "", "templates": [t.slug]})
                entry["hint"] = entry["hint"] or hint
    return found


def merge_placeholders(per_template: list) -> dict:
    """Combine ``extract_placeholders`` results: the first non-empty hint, all templates, sorted by name."""
    merged = {}
    for placeholders in per_template:
        for name, entry in placeholders.items():
            target = merged.setdefault(name, {"hint": "", "templates": []})
            target["hint"] = target["hint"] or entry["hint"]
            target["templates"] += [s for s in entry["templates"] if s not in target["templates"]]
    return {name: merged[name] for name in sorted(merged)}


def extract_forbidden(t: Template) -> list:
    """Rows ``{template, pattern_text, violates, severity}`` from tables whose header starts with «Формулировка».

    ``severity`` is ``risk`` when «Что нарушает» calls the wording a «зона риска» (not an undisputed
    violation), else ``violation``.
    """
    rows = []
    for text in t.sections.values():
        for table in tables(text):
            if table.header[0].startswith(FORBIDDEN_HEADER_START) and len(table.header) >= 2:
                for cells in table.rows:
                    violates = plain(cells[1])
                    severity = "risk" if _RISK.search(violates) else "violation"
                    rows.append(
                        {"template": t.slug, "pattern_text": plain(cells[0]), "violates": violates, "severity": severity}
                    )
    return rows


# ------------------------------------------------------------------ files


def clean(md: str, ctx: LinkCtx) -> str:
    """Rewrite links and process markers outside fenced blocks; fenced blocks stay as they are."""
    return "\n".join(text if fenced else scrub(sanitize(text, ctx)) for fenced, text in segments(md))


def outline(md: str) -> list:
    """``[(level, title)]`` of the level-2 and level-3 headings outside fenced blocks."""
    result = []
    for fenced, text in segments(md):
        if not fenced:
            result += [(len(m.group(1)), m.group(2)) for m in map(_HEADING.match, text.split("\n")) if m]
    return result


def anchor(title: str) -> str:
    """GitHub-style heading anchor: lower case, punctuation dropped, spaces to hyphens."""
    kept = [
        ch for ch in re.sub(r"`([^`]*)`", r"\1", title).lower()
        if ch.isalnum() or ch in "-_ " or unicodedata.category(ch).startswith("M")
    ]
    return "".join(kept).replace(" ", "-")


def toc(md: str, depth: int = 3) -> str:
    """Block ``## Оглавление``: links to the level-2 headings and, when ``depth`` is 3, their level-3 headings.

    The anchors follow GitHub's rules, including the suffix of a repeated heading.
    """
    seen, lines = {}, ["## Оглавление", ""]
    for level, title in outline(md):
        base = anchor(title)
        count = seen.get(base, 0)
        seen[base] = count + 1
        if level <= depth:
            lines.append(f"{'  ' * (level - 2)}- [{title}](#{base if count == 0 else f'{base}-{count}'})")
    return "\n".join(lines)


def _meta_frontmatter(t: Template, ctx: LinkCtx) -> str:
    lines = ["---", f"template: {t.slug}"]
    lines += [clean(t.fm_raw[key], ctx) for key in META_FRONTMATTER if key in t.fm_raw]
    return "\n".join(lines + ["---"])


def _file(t: Template, sections: tuple, ctx: LinkCtx, frontmatter: str = "") -> str:
    """Text of ``text.md`` or ``meta.md``: head of the template, then the chosen sections in order.

    A file that would have more than ``TOC_MIN_LINES`` lines (``str.splitlines``) gets a table of
    contents right after the head.
    """
    body = []
    for number in sections:
        found = t.section(number)
        if found:
            body += [f"## {found[0]}", "", clean(found[1], ctx), ""]
    note = (
        "Обозначения вида А4 или Б2 в тексте — элементы этого шаблона в `elements.json` "
        f"(поле `template`: `{t.slug}`)."
    )
    head = ([frontmatter] if frontmatter else []) + ([clean(t.head, ctx)] if t.head else [])
    tail = [note, "\n".join(body).rstrip("\n")]
    document = "\n\n".join(head + tail) + "\n"
    if len(document.splitlines()) > TOC_MIN_LINES:
        document = "\n\n".join(head + [toc(document)] + tail) + "\n"
    return document


def render_text(t: Template, ctx: LinkCtx) -> str:
    return _file(t, TEXT_SECTIONS, ctx)


def render_meta(t: Template, ctx: LinkCtx) -> str:
    return _file(t, META_SECTIONS, ctx, _meta_frontmatter(t, ctx))


def _json_lines(items: list) -> str:
    """JSON array, one compact row per line."""
    rows = [json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in items]
    return "[\n" + ",\n".join(rows) + "\n]\n"


def _json_map(mapping: dict) -> str:
    """JSON object, one compact entry per line."""
    rows = [
        f"{json.dumps(key, ensure_ascii=False)}:{json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
        for key, value in mapping.items()
    ]
    return "{\n" + ",\n".join(rows) + "\n}\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _remove(out: Path, rel: str) -> None:
    """Delete a generated file and the folders it leaves empty (never ``out`` itself)."""
    path = out / rel
    path.unlink()
    folder = path.parent
    while folder != out and folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        folder = folder.parent


def render_readme(templates: list, elements: list, placeholders: dict) -> str:
    """``templates/README.md``: index of the templates, how to read the indexes, placeholders without a hint."""
    body = [
        "## Индекс",
        "",
        "Тексты в `text.md` — основа документа для владельца: плейсхолдеры `{{ИМЯ}}` заменяются реальными "
        "данными, блоки в квадратных скобках зависят от продукта. В `meta.md` — когда шаблон нужен, "
        "что заполнить и спорные места с вариантами; решение по ним остаётся за владельцем.",
        "",
    ]
    for t in templates:
        mine = [row for row in elements if row["template"] == t.slug]
        counts = ", ".join(f"{s} {sum(1 for r in mine if r['status'] == s)}" for s in STATUSES)
        text = t.section_text(3)
        subsections = [title for level, title in outline(text) if level == 3]
        body += [
            f"### {t.slug}",
            "",
            f"{plain(t.fm.get('title', t.slug))}. [text.md]({t.slug}/{TEXT_FILE}), [meta.md]({t.slug}/{META_FILE}). "
            f"Редакция {t.fm.get('updated', '—')}, проверено {t.fm.get('verified', '—')}.",
            f"- Элементов в `elements.json`: {len(mine)} ({counts}).",
            f"- Блоков markdown в `text.md`: {len(fenced_blocks(text))}."
            + (f" Подразделы: {'; '.join(subsections)}." if subsections else ""),
            "",
        ]
    body += [
        "## Как читать данные шаблонов",
        "",
        "- `elements.json` — строка на элемент раздела «Обязательное содержание» шаблона. `status` — "
        "обязательно, при условии или рекомендуется, как отмечено в шаблоне; `qualifier` — условие или оговорка. "
        "`method` — на чём держится элемент: `norm`, `practice` (инженерная практика, а также пустая ячейка "
        "«Норма»), `interpretation` (трактовка, позиция органа, не норма), `inference` (вывод), `platform` (правило "
        "магазина или площадки). Как «обязательный» элемент подаётся только при `status` «обязательно», "
        "`method` `norm` и источнике из базы или с официальным URL. `requirements` — id карточек (`ru:<slug>`, "
        "файл `../cards/<slug>.md`).",
        "- `placeholders.json` — плейсхолдеры всех шаблонов: подсказка (что вписать) и шаблоны, где имя встречается.",
        "- `forbidden-clauses.json` — формулировки, которых не должно быть в документе, и что они нарушают; "
        "`severity`: `violation` или `risk` (зона риска, не бесспорное нарушение).",
        "",
        "## Плейсхолдеры без подсказки",
        "",
    ]
    missing = {name: entry["templates"] for name, entry in placeholders.items() if not entry["hint"]}
    body += [
        "В таблицах «Что заполнить» этих плейсхолдеров нет, поэтому подсказки у них нет; смысл виден по месту в "
        f"тексте шаблона. Всего {len(missing)} из {len(placeholders)}.",
        "",
    ]
    for t in templates:
        names = [f"`{{{{{name}}}}}`" for name, slugs in missing.items() if t.slug in slugs]
        if names:
            body.append(f"- {t.slug}: {', '.join(names)}")
    document = "\n".join(body)
    return "\n".join(["# Шаблоны документов (ru)", "", toc(document, depth=2), "", document]).rstrip("\n") + "\n"


def generated_paths(root) -> set:
    """Paths (relative, posix) of the files this module writes that exist under ``root``."""
    root = Path(root)
    paths = {name for name in INDEX_FILES if (root / name).is_file()}
    folder = root / "templates"
    if folder.is_dir():
        for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
            paths |= {f"templates/{sub.name}/{n}" for n in (TEXT_FILE, META_FILE) if (sub / n).is_file()}
    return paths


def build_templates(topic, out, ctx: LinkCtx) -> dict:
    """Write templates and indexes of the topic into ``out`` (the pack directory) and return the build facts.

    ``ctx`` supplies the card slugs and the map of raw files; links inside the written files are
    relative to ``templates/<t>/``. A file in ``references`` without a «Шаблон текста» section is not
    a template and is skipped (listed under ``skipped``). Without any template nothing is written,
    and files left by earlier builds are removed.
    """
    out = Path(out)
    found = load_templates(topic)
    templates = [t for t in found if t.section(3)]
    skipped = [t.slug for t in found if not t.section(3)]
    local = LinkCtx(
        card_slugs=set(ctx.card_slugs),
        template_slugs={t.slug for t in templates},
        raw_urls=ctx.raw_urls,
        card_href=lambda slug: f"../../cards/{slug}.md",
        template_href=lambda slug: f"../{slug}/{TEXT_FILE}",
    )

    elements = [row for t in templates for row in extract_elements(t)]
    unknown = sorted({r for row in elements for r in row["requirements"] if r[3:] not in local.card_slugs})
    if unknown:
        raise TemplateError(f"elements refer to unknown cards: {', '.join(unknown)}")
    placeholders = merge_placeholders([extract_placeholders(t) for t in templates])
    forbidden = [row for t in templates for row in extract_forbidden(t)]

    written = {f"templates/{t.slug}/{name}" for t in templates for name in (TEXT_FILE, META_FILE)}
    for t in templates:
        _write(out / "templates" / t.slug / TEXT_FILE, render_text(t, local))
        _write(out / "templates" / t.slug / META_FILE, render_meta(t, local))
    if templates:
        written |= set(INDEX_FILES)
        _write(out / "elements.json", _json_lines(elements))
        _write(out / "placeholders.json", _json_map(placeholders))
        _write(out / "forbidden-clauses.json", _json_lines(forbidden))
        _write(out / "templates" / "README.md", render_readme(templates, elements, placeholders))
    for rel in generated_paths(out) - written:  # files of templates that are gone
        _remove(out, rel)

    return {
        "templates": len(templates),
        "skipped": skipped,
        "tables": sum(len(element_tables(t)) for t in templates),
        "elements": len(elements),
        "statuses": {s: sum(1 for r in elements if r["status"] == s) for s in STATUSES},
        "methods": {m: sum(1 for r in elements if r["method"] == m) for m in METHODS},
        "placeholders": len(placeholders),
        "placeholders_without_hint": sorted(n for n, e in placeholders.items() if not e["hint"]),
        "forbidden": len(forbidden),
    }
