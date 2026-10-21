"""Writers for the generated pack: requirements.jsonl, cards/<slug>.md and BASE.md."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .dates import norm_dates
from .links import LinkCtx, sanitize, unlink
from .parse import Card, parse_frontmatter, read_text
from .prose import scrub
from .tech import cannot_check_items, classify_tech

SECTION_BASIS = "Правовое основание"
SECTION_TECH = "Техническое проявление в продукте"
SECTION_CANNOT_CHECK = "Что нельзя проверить по репозиторию"
DROPPED_SECTIONS = {"See Also", "Sources"}
DROPPED_FRONTMATTER = {"sources", "created", "aliases", "tags", "confidence"}
# Every generated card starts with these two lines; hand-written files next to them do not.
GENERATED_CARD_MARK = "---\nid: ru:"

# Hosts that mirror official texts; a card may list them, but they are not official sources.
NON_OFFICIAL_HOSTS = {
    "sudact.ru", "www.garant.ru", "garant.ru", "www.consultant.ru", "consultant.ru",
    "xn--90afdbaav0bd1afy6eub5d.xn--p1ai",
}

# requirements.jsonl is an index. Titles, summaries, acts, norm dates and official URLs are always
# complete. The two item lists are the only part that gives way: when a line would exceed
# LINE_BUDGET characters, whole tech and cannot_check items are left out (at least one stays).
# Item text is at most ITEM_LIMIT characters.
LINE_BUDGET = 2750
ITEM_LIMIT = 200
# Order in which the two lists receive one more item while the line has room.
_GROWTH_ORDER = ("tech", "cannot_check")

_URL = re.compile(r"https?://[^\s)<>\]]+")


def dumps(record: dict) -> str:
    """One compact JSON object, non-ASCII text kept as is."""
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def dir_letter(dirs: dict) -> dict:
    """Map every slug to the letter of the directory that lists it; a slug in two directories is an error."""
    result = {}
    for letter, (_, _, slugs) in dirs.items():
        for slug in slugs:
            if slug in result:
                raise ValueError(f"slug {slug!r} is listed in directories {result[slug]} and {letter}")
            result[slug] = letter
    return result


def official_urls(basis_md: str) -> list:
    """Every http(s) URL of the legal-basis section, in order and without duplicates.

    URLs in the list of official URLs and in the rows of the norm table both count. Lines that
    announce unofficial copies are skipped, and so are mirrors of official texts.
    """
    urls = []
    for line in basis_md.split("\n"):
        if "неофициальн" in line.lower():
            continue
        for url in _URL.findall(line):
            url = url.rstrip(".,;:")
            host = re.match(r"https?://([^/?#]+)", url).group(1).lower()
            if host not in NON_OFFICIAL_HOSTS and url not in urls:
                urls.append(url)
    return urls


def _text(value: str) -> str:
    """Single-line field of a record: links reduced to text, process markers reworded."""
    return scrub(unlink(value))


def brief(
    card: Card, trigger: str, dir: str, templates_by_card: dict, ctx=None  # noqa: A002 - name fixed by the contract
) -> dict:
    """Short requirement record for requirements.jsonl.

    ``ctx`` is the link context the card is written with. The official URLs are read from the
    legal-basis section as it appears in the written card, so a link into a raw file counts with
    the official URL it was turned into. Without ``ctx`` the section is read as it stands.

    Everything except the two item lists is complete. ``tech`` and ``cannot_check`` receive whole
    items, in card order, while the line stays within ``LINE_BUDGET``; each keeps at least one
    item (the full lists are in the card). Item text is at most ``ITEM_LIMIT`` characters and a
    qualifier clause is never cut. ``tech`` kinds are capped by the ``source_kind`` of the card.
    """
    fm = card.fm
    basis = card.sections.get(SECTION_BASIS, "")
    basis = scrub(sanitize(basis, ctx) if ctx is not None else basis)
    record = {
        "id": f"ru:{card.slug}",
        "dir": dir,
        "title": _text(fm.get("title", "")),
        "summary": _text(fm.get("summary", "")),
        "trigger": _text(trigger),
        "obligation": fm.get("obligation", ""),
        "source_kind": fm.get("source_kind", ""),
        "legal_confidence": fm.get("legal_confidence", ""),
        "volatility": fm.get("volatility", ""),
        "subjects": list(fm.get("subjects", [])),
        "models": list(fm.get("models", [])),
        "products": list(fm.get("products", [])),
        "acts": [_text(act) for act in fm.get("acts", [])],
        "effective_from": fm.get("effective_from", ""),
        "norm_dates": norm_dates(basis),
        "official_urls": official_urls(basis),
        "tech": [],
        "cannot_check": [],
        "templates": list(templates_by_card.get(card.slug, [])),
        "card": f"cards/{card.slug}.md",
    }
    candidates = {
        "tech": classify_tech(
            scrub(card.sections.get(SECTION_TECH, "")), ITEM_LIMIT, source_kind=fm.get("source_kind", "")
        ),
        "cannot_check": cannot_check_items(scrub(card.sections.get(SECTION_CANNOT_CHECK, "")), ITEM_LIMIT),
    }
    take = {key: min(1, len(items)) for key, items in candidates.items()}

    def render() -> int:
        for key, items in candidates.items():
            record[key] = items[: take[key]]
        return len(dumps(record))

    render()
    growing = True
    while growing:
        growing = False
        for key in _GROWTH_ORDER:
            if take[key] < len(candidates[key]):
                take[key] += 1
                if render() <= LINE_BUDGET:
                    growing = True
                else:
                    take[key] -= 1
    render()
    return record


def load_templates(topic):
    """Read the templates of the knowledge base.

    Returns ``(templates_by_card, template_dates)``: for every card the sorted template slugs
    that list it among their sources, and for every template its ``updated`` date.
    """
    by_card, dates = {}, {}
    for path in sorted((Path(topic) / "wiki" / "references").glob("shablon-*.md")):
        template = path.stem[len("shablon-"):]
        fm, _ = parse_frontmatter(read_text(path))
        dates[template] = fm.get("updated", "")
        for source in fm.get("sources", []):
            match = re.fullmatch(r"wiki/concepts/([\w-]+)\.md", source)
            if match:
                by_card.setdefault(match.group(1), []).append(template)
    return {slug: sorted(names) for slug, names in by_card.items()}, dates


def is_generated_card(path) -> bool:
    """True when the file was written by ``write_card``."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read(len(GENERATED_CARD_MARK)) == GENERATED_CARD_MARK


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def write_requirements(records: list, out) -> Path:
    """Write ``requirements.jsonl`` into the pack directory, sorted by id."""
    path = Path(out) / "requirements.jsonl"
    lines = [dumps(record) for record in sorted(records, key=lambda r: r["id"])]
    _write_text(path, "\n".join(lines) + "\n")
    return path


def write_card(card: Card, ctx: LinkCtx, out) -> Path:
    """Write ``cards/<slug>.md``: kept frontmatter plus the body without See Also and Sources.

    Links and process markers are rewritten in the frontmatter values and in the body alike.
    """
    def clean(text: str) -> str:
        return scrub(sanitize(text, ctx))

    parts = ["---", f"id: ru:{card.slug}"]
    parts += [clean(raw) for key, raw in card.fm_raw.items() if key not in DROPPED_FRONTMATTER]
    parts += ["---", ""]
    if card.head:
        parts += [clean(card.head), ""]
    for title, content in card.sections.items():
        if title in DROPPED_SECTIONS:
            continue
        parts += [f"## {title}", "", clean(content), ""]
    path = Path(out) / "cards" / f"{card.slug}.md"
    _write_text(path, "\n".join(parts).rstrip("\n") + "\n")
    return path


def write_base(meta: dict, out) -> Path:
    """Write ``BASE.md``: plain facts about the build."""
    lines = [
        "# Knowledge base (ru)",
        "",
        f"- Base date: {meta['base_date']}",
        f"- Source content sha256: {meta['source_sha256']}",
        f"- Requirements: {meta['requirements']}",
        f"- Cards: {meta['cards']}",
        f"- Templates: {meta['templates']}",
        f"- Generator version: {meta['generator_version']}",
    ]
    path = Path(out) / "BASE.md"
    _write_text(path, "\n".join(lines) + "\n")
    return path
