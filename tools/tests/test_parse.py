"""Unit tests for kb.parse (frontmatter, sections, card loading)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.parse import Card, header_bytes, load_card, parse_frontmatter, split_sections  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TOPIC = FIXTURES / "topic"


def test_fenced_headings_ignored():
    body = (
        "preamble\n\n"
        "## Real\ntext\n"
        "```\n## Fake in backticks\nmore\n```\n"
        "~~~md\n## Fake in tildes\n~~~\n"
        "after\n"
        "## Second\nbody\n"
    )
    sections = split_sections(body)
    assert list(sections) == ["Real", "Second"]
    assert "## Fake in backticks" in sections["Real"]
    assert "## Fake in tildes" in sections["Real"]
    assert "after" in sections["Real"]
    assert sections["Second"] == "body"


def test_only_requested_level_splits():
    body = "## A\none\n### A.1\nsub\n## B\ntwo\n"
    assert list(split_sections(body)) == ["A", "B"]
    assert "### A.1" in split_sections(body)["A"]
    assert list(split_sections(body, level=3)) == ["A.1"]


def test_frontmatter_shapes():
    text = (
        "---\n"
        'title: "A, b: c"\n'
        "sources:\n"
        "  - raw/x.md\n"
        "  - raw/y.md\n"
        "tags: [one, two]\n"
        'acts: ["x, y", "z"]\n'
        "effective_from: mixed\n"
        "checked: 2026-09-29\n"
        "empty_list: []\n"
        "---\n"
        "# Heading\nbody\n"
    )
    fm, body = parse_frontmatter(text)
    assert fm["title"] == "A, b: c"
    assert fm["sources"] == ["raw/x.md", "raw/y.md"]
    assert fm["tags"] == ["one", "two"]
    assert fm["acts"] == ["x, y", "z"]
    assert fm["effective_from"] == "mixed"
    assert fm["checked"] == "2026-09-29"
    assert fm["empty_list"] == []
    assert body.startswith("# Heading")


def test_no_frontmatter_returns_empty_dict():
    fm, body = parse_frontmatter("# Just a heading\n")
    assert fm == {}
    assert body == "# Just a heading\n"


def test_load_card_fixture():
    card = load_card(TOPIC / "wiki" / "concepts" / "demo-consent.md")
    assert isinstance(card, Card)
    assert card.slug == "demo-consent"
    assert card.fm["obligation"] == "conditional"
    assert card.fm["subjects"] == ["ul", "ip"]
    assert card.fm["acts"] == ["Тест-ФЗ ст. 1 ч. 1, 2", "Тест-ПП № 5 п. 3"]
    assert list(card.sections)[:3] == ["Суть требования", "Кому и когда применяется", "Исключения"]
    # The fenced pseudo-heading stays inside its real section.
    assert "## Не заголовок внутри ограждения" in card.sections["Суть требования"]
    assert "Sources" in card.sections and "See Also" in card.sections
    # Preamble (H1 + intro quote) is kept separately for emitting.
    assert card.head.startswith("# Демо: согласие на тестовую обработку")
    # Original frontmatter entries are kept verbatim for emitting.
    assert card.fm_raw["acts"] == 'acts: ["Тест-ФЗ ст. 1 ч. 1, 2", "Тест-ПП № 5 п. 3"]'
    assert card.fm_raw["sources"].startswith("sources:\n  - raw/articles/demo-official.md")


def test_byte_order_mark_is_dropped(tmp_path):
    path = tmp_path / "card.md"
    path.write_bytes(b"\xef\xbb\xbf---\ntitle: \"T\"\nobligation: general\n---\n\n# T\n\n## A\ntext\n")
    card = load_card(path)
    assert card.fm == {"title": "T", "obligation": "general"}
    assert card.sections == {"A": "text"}
    assert header_bytes(path) == b'---\ntitle: "T"\nobligation: general\n---\n'


def test_header_bytes_without_frontmatter_is_empty(tmp_path):
    path = tmp_path / "plain.md"
    path.write_text("# no frontmatter\n", encoding="utf-8")
    assert header_bytes(path) == b""
