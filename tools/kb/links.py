"""Link rewriting for the public pack: wikilinks, relative links and raw-file links."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .parse import header_bytes, parse_frontmatter

RAW_LABEL = "raw"
SOURCE_LABEL = "источник"
_SENTINEL = ""


def _default_card_href(slug: str) -> str:
    return f"{slug}.md"


def _default_template_href(slug: str) -> str:
    return f"../templates/{slug}/text.md"


@dataclass
class LinkCtx:
    """What the sanitizer needs to know about the pack it writes into.

    ``card_href`` and ``template_href`` give the link target of a card or template slug,
    relative to the file that contains the link.
    """

    card_slugs: set
    template_slugs: set
    raw_urls: dict
    card_href: Callable[[str], str] = _default_card_href
    template_href: Callable[[str], str] = _default_template_href
    _known_hrefs: set = field(default_factory=set, init=False, repr=False)

    def __post_init__(self):
        self._known_hrefs = {self.card_href(s) for s in self.card_slugs} | {
            self.template_href(s) for s in self.template_slugs
        }


_TOKEN = re.compile(
    r"\[\[(?P<ws>[^\]|#]+?)(?:#[^\]|]*)?(?:\|(?P<wt>[^\]]*))?\]\]"
    r"(?P<tail>[ \t]*\(\[[^\]]*\]\([^)\s]*\)\))?"
    r"|\[(?P<label>[^\[\]]*)\]\((?P<target>[^)\s]*)\)"
)
_BARE_RAW = re.compile(
    r"(?:,[ \t]*|[ \t]+)?`?(?<![\w/.\-])raw/(?:articles|notes|data|papers|repos)/[\w.\-]+`?"
)
_CLEANUP = [
    (re.compile(r"[ \t]*\(" + _SENTINEL + r"\)"), ""),
    (re.compile(r"\(" + _SENTINEL + r";[ \t]*"), "("),
    (re.compile(r"[ \t]*[—–-][ \t]*" + _SENTINEL), ""),
    (re.compile(_SENTINEL + r"[ \t]*[;,][ \t]*"), ""),
    (re.compile(r"[ \t]*" + _SENTINEL), ""),
]
_SIBLING = re.compile(r"[^/]+\.md")


def _first_url(source: str):
    """The URL of a ``source:`` value; a value listing several URLs separated by « ; » gives the first."""
    match = re.match(r"(https?://[^\s;]+)\s*(?:;.*)?$", source.strip())
    return match.group(1) if match else None


def raw_url_map(topic) -> dict:
    """Map ``raw/<dir>/<file>.md`` to the official URL in the ``source:`` of that raw file.

    Files whose ``source_kind`` is ``secondary`` and sources that are not an http(s) URL are left
    out, so a link never points at a secondary page presented as a source. If a source lists
    several URLs, the first one is used.
    """
    topic = Path(topic)
    result = {}
    for path in sorted((topic / "raw").rglob("*.md")):
        if path.name == "_index.md":
            continue
        fm, _ = parse_frontmatter(header_bytes(path).decode("utf-8-sig"))
        source = fm.get("source", "")
        url = _first_url(source) if isinstance(source, str) else None
        if url and fm.get("source_kind") != "secondary":
            result[path.relative_to(topic).as_posix()] = url
    return result


_TEMPLATE_PREFIX = "shablon-"


def _template_name(slug: str, ctx: LinkCtx):
    if slug.startswith(_TEMPLATE_PREFIX) and slug[len(_TEMPLATE_PREFIX):] in ctx.template_slugs:
        return slug[len(_TEMPLATE_PREFIX):]
    return None


def _link_to(slug: str, text: str, ctx: LinkCtx) -> str:
    """Link to a card, or to a template when the slug is a ``shablon-`` reference; else plain text.

    Template slugs coincide with card slugs, so a bare slug always means the card.
    """
    text = text or slug
    if slug in ctx.card_slugs:
        return f"[{text}]({ctx.card_href(slug)})"
    template = _template_name(slug, ctx)
    if template:
        return f"[{text}]({ctx.template_href(template)})"
    return text


def _replace_link(label: str, target: str, ctx: LinkCtx) -> str:
    if re.match(r"^(?:https?://|mailto:|#)", target) or target in ctx._known_hrefs:
        return f"[{label}]({target})"
    path = target.split("#", 1)[0]
    if _SIBLING.fullmatch(path):
        return _link_to(path[:-3], label, ctx)
    if path.startswith("../references/"):
        template = _template_name(Path(path).stem, ctx)
        return f"[{label}]({ctx.template_href(template)})" if template else label
    stripped = re.sub(r"^(?:\.\./)+", "", path)
    if stripped.startswith("raw/"):
        url = ctx.raw_urls.get(stripped)
        is_raw_label = label.strip().lower() == RAW_LABEL
        if url:
            return f"[{SOURCE_LABEL if is_raw_label else label}]({url})"
        return _SENTINEL if is_raw_label else label
    return label


def sanitize(md: str, ctx: LinkCtx) -> str:
    """Rewrite links of a card body so that it stands alone inside the public pack.

    A wikilink (with or without its trailing parenthetical link) becomes an ordinary link to
    the card or template, or plain text for anything else. Relative links to other cards go
    through ``ctx.card_href``; hub and other reference links are dropped keeping the text.
    Links into raw files become the official URL of the raw file, or disappear. Bare raw
    paths are deleted.
    """

    def substitute(match):
        if match.group("ws") is not None:
            slug = match.group("ws").strip()
            text = (match.group("wt") or "").strip()
            return _link_to(slug, text, ctx)
        return _replace_link(match.group("label"), match.group("target"), ctx)

    out = _TOKEN.sub(substitute, md)
    out = _BARE_RAW.sub("", out)
    if _SENTINEL in out:
        for pattern, replacement in _CLEANUP:
            out = pattern.sub(replacement, out)
    return out


_EMPTY_CTX = LinkCtx(set(), set(), {})
_MD_LINK = re.compile(r"\[([^\[\]]*)\]\([^)\s]*\)")
_EMPHASIS = re.compile(r"\*\*|__|`")


def unlink(md: str) -> str:
    """Reduce every link to its text (wikilinks, relative links, raw links and URLs alike)."""
    return _MD_LINK.sub(r"\1", sanitize(md, _EMPTY_CTX))


def plain_text(md: str) -> str:
    """Return markdown as one line of plain text: links reduced to their text, emphasis removed."""
    return re.sub(r"\s+", " ", _EMPHASIS.sub("", unlink(md))).strip()
