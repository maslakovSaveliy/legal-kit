"""Unit tests for kb.links (wikilinks, relative links, raw links, bare raw paths)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.links import LinkCtx, raw_url_map, sanitize  # noqa: E402

TOPIC = Path(__file__).resolve().parent / "fixtures" / "topic"


def make_ctx(**overrides):
    params = dict(
        card_slugs={"politika", "soglasie"},
        template_slugs={"forma"},
        raw_urls={"raw/articles/a.md": "https://example.gov/doc/1"},
        card_href=lambda slug: f"{slug}.md",
        template_href=lambda slug: f"../templates/{slug}/text.md",
    )
    params.update(overrides)
    return LinkCtx(**params)


def test_dual_and_lone_wikilink():
    ctx = make_ctx()
    md = (
        "См. [[politika|политика обработки]] ([Политика ПДн](politika.md)) далее. "
        "Скобка ([[soglasie|карточка]]) и хаб [[hub-x|Хаб]] ([Хаб](../topics/hub-x.md))."
    )
    out = sanitize(md, ctx)
    assert out == (
        "См. [политика обработки](politika.md) далее. "
        "Скобка ([карточка](soglasie.md)) и хаб Хаб."
    )
    assert "[[" not in out and "../topics" not in out


def test_lone_wikilink_without_alias_uses_slug_text():
    ctx = make_ctx()
    assert sanitize("[[politika]] и [[nowhere]]", ctx) == "[politika](politika.md) и nowhere"


def test_sibling_card_link_goes_through_card_href():
    ctx = make_ctx(card_href=lambda slug: f"cards/{slug}.md")
    md = "[Согласие](soglasie.md), [Чужая](ghost.md)"
    out = sanitize(md, ctx)
    assert out == "[Согласие](cards/soglasie.md), Чужая"
    # Second pass does not damage already rewritten links.
    assert sanitize(out, ctx) == out


def test_template_links():
    ctx = make_ctx()
    md = "[[shablon-forma|шаблон]] и [форма](../references/shablon-forma.md) и [карта](../references/karta-pokrytiya.md)"
    out = sanitize(md, ctx)
    assert out == "[шаблон](../templates/forma/text.md) и [форма](../templates/forma/text.md) и карта"


def test_topics_link_dropped():
    ctx = make_ctx()
    out = sanitize("см. [Хаб направления](../topics/hub-x.md) здесь", ctx)
    assert out == "см. Хаб направления здесь"


def test_raw_link_to_official_url():
    ctx = make_ctx()
    out = sanitize("Приказ ([Текст приказа](../../raw/articles/a.md)); также [raw](../../raw/articles/a.md).", ctx)
    assert out == "Приказ ([Текст приказа](https://example.gov/doc/1)); также [источник](https://example.gov/doc/1)."
    assert "raw/" not in out


def test_raw_link_without_url_is_removed():
    ctx = make_ctx()
    cases = {
        "Автор ([Заметка P4](../../raw/notes/n.md)) писал": "Автор (Заметка P4) писал",
        "Текст — [raw](../../raw/notes/n.md). Далее": "Текст. Далее",
        "Суд ([raw](../../raw/notes/n.md)). Далее": "Суд. Далее",
        "Суд ([raw](../../raw/notes/n.md); дата 5) тут": "Суд (дата 5) тут",
    }
    for src, expected in cases.items():
        assert sanitize(src, ctx) == expected, src


def test_bare_raw_path_removed():
    ctx = make_ctx()
    src = "не содержит, `raw/articles/2026-10-16-x.md`); режим данных"
    assert sanitize(src, ctx) == "не содержит); режим данных"
    assert "raw/" not in sanitize("см. raw/notes/z.md для деталей", ctx)


def test_external_links_untouched():
    ctx = make_ctx()
    md = "[ИПС](http://example.gov/x?a=1&b=2)"
    assert sanitize(md, ctx) == md


def test_sanitize_is_idempotent():
    ctx = make_ctx()
    md = (
        "[[politika|п]] ([П](politika.md)) [raw](../../raw/articles/a.md) "
        "[Х](../topics/x.md) ([raw](../../raw/notes/n.md)) `raw/articles/q.md`"
    )
    once = sanitize(md, ctx)
    assert sanitize(once, ctx) == once


def test_raw_url_map_reads_only_http_non_secondary_sources_and_takes_the_first_url():
    urls = raw_url_map(TOPIC)
    assert urls == {
        "raw/articles/demo-official.md": "https://example.gov/doc/1",
        "raw/articles/demo-multi.md": "https://example.gov/first",
    }


def test_template_slug_equal_to_card_slug_means_the_card_for_bare_slugs():
    ctx = make_ctx(card_slugs={"soglasie"}, template_slugs={"soglasie"})
    out = sanitize("[[soglasie|карточка]], [c](soglasie.md), [t](../references/shablon-soglasie.md)", ctx)
    assert out == "[карточка](soglasie.md), [c](soglasie.md), [t](../templates/soglasie/text.md)"
