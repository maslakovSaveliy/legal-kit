"""Tests for the template generator: unit tests on synthetic templates, integration tests on the real topic.

Integration tests read the topic path from LEGAL_KIT_WIKI (and the table module from LEGAL_KIT_BUILD_REFS,
see wiki_env.py) and are skipped when it is unset.
"""

import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from kb import templates as tpl  # noqa: E402
from kb.links import LinkCtx, raw_url_map  # noqa: E402
from wiki_env import BUILD_REFS, SKIP_REASON, WIKI  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "templates"
FORM = FIXTURES / "shablon-demo-form.md"
OTHER = FIXTURES / "shablon-demo-other.md"
RAW_URL = "https://example.gov/doc/1"
FORBIDDEN_IN_PACK = (
    "raw/articles", "raw/notes", "[[", "../topics/", "/Us" + "ers/", "llm" + "-wiki", "wiki/concepts", "wiki/references",
    "](../concepts",
)


def make_ctx(**overrides):
    params = dict(
        card_slugs={"demo-consent", "demo-policy"},
        template_slugs={"demo-form", "demo-other"},
        raw_urls={"raw/articles/demo-official.md": RAW_URL},
        card_href=lambda slug: f"../../cards/{slug}.md",
        template_href=lambda slug: f"../{slug}/text.md",
    )
    params.update(overrides)
    return LinkCtx(**params)


@pytest.fixture()
def topic(tmp_path):
    """A topic folder holding the synthetic templates (and a file that is not a template)."""
    folder = tmp_path / "topic" / "wiki" / "references"
    folder.mkdir(parents=True)
    for source in (FORM, OTHER, FIXTURES / "shablon-not-a-template.md"):
        shutil.copy(source, folder / source.name)
    return tmp_path / "topic"


def element(rows, element_id):
    return next(row for row in rows if row["id"] == element_id)


# ------------------------------------------------------------------ loading and parsing


def test_load_template_strips_prefix_and_reads_sections():
    t = tpl.load_template(FORM)
    assert t.slug == "demo-form"
    assert t.fm["title"] == "Шаблон: демо-форма"
    assert t.fm["confidence"] == "medium"
    heading, text = t.section(3)
    assert heading == "3. Шаблон текста"
    assert "### 3.1. Уведомление" in text
    assert t.section(9) is None
    assert t.section_text(9) == ""


def test_headings_inside_fenced_blocks_do_not_split_sections():
    t = tpl.load_template(FORM)
    assert [h[:2] for h in t.sections] == ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8."]
    assert "## 1. Продавец" in t.section_text(3)


def test_segments_join_back_and_mark_fences():
    md = "до\n\n```markdown\n# в блоке\n```\n\nпосле\n~~~\nещё\n~~~"
    parts = tpl.segments(md)
    assert [fenced for fenced, _ in parts] == [False, True, False, True]
    assert "\n".join(text for _, text in parts) == md


def test_unclosed_fence_runs_to_the_end():
    parts = tpl.segments("a\n```\nb\nc")
    assert [fenced for fenced, _ in parts] == [False, True]


def test_fenced_blocks_return_info_and_body():
    t = tpl.load_template(FORM)
    blocks = tpl.fenced_blocks(t.section_text(3))
    assert [info for info, _ in blocks] == ["markdown", "markdown", "markdown"]
    assert blocks[1][1].startswith("# Согласие\nВерсия")
    assert blocks[1][1].endswith("как есть.")


def test_split_row_keeps_wikilink_bar_and_unescapes_bar():
    row = "| А1. Текст | обязательно | 152-ФЗ \\| ст. 5 | [[a|Название]] ([карточка](../concepts/a.md)) |"
    cells = tpl.split_row(row)
    assert cells == ["А1. Текст", "обязательно", "152-ФЗ | ст. 5", "[[a|Название]] ([карточка](../concepts/a.md))"]
    assert tpl.split_row("| a | |") == ["a", ""]
    assert tpl.split_row("| a | b") == ["a", "b"]


def test_tables_skip_fenced_blocks_and_check_width():
    md = "| a | b |\n|---|---|\n| 1 | 2 |\n\n```\n| x | y |\n|---|---|\n| 3 | 4 |\n```\n"
    found = tpl.tables(md)
    assert len(found) == 1 and found[0].header == ["a", "b"] and found[0].rows == [["1", "2"]]
    with pytest.raises(tpl.TemplateError):
        tpl.tables("| a | b |\n|---|---|\n| 1 | 2 | 3 |\n")


def test_element_tables_are_found_in_section_two_only():
    t = tpl.load_template(FORM)
    assert len(tpl.element_tables(t)) == 2
    assert sum(len(table.rows) for table in tpl.element_tables(t)) == 11


# ------------------------------------------------------------------ elements


def test_elements_sorted_by_section_letter_then_number():
    rows = tpl.extract_elements(tpl.load_template(FORM))
    assert [row["id"] for row in rows] == [
        "А1", "А2", "А3", "А4", "А5", "А6", "А7", "А10", "Б2", "Б3", "Б10",
    ]
    assert {row["template"] for row in rows} == {"demo-form"}
    assert [row["section"] for row in rows][-3:] == ["Б", "Б", "Б"]


def test_element_fields_follow_the_schema():
    rows = tpl.extract_elements(tpl.load_template(FORM))
    first = element(rows, "А1")
    assert list(first) == ["template", "id", "section", "text", "status", "qualifier", "method", "norm", "requirements"]
    assert first["text"] == "Для каждой цели определено основание"
    assert first["status"] == "обязательно"
    assert first["qualifier"] == ""
    assert first["norm"] == "152-ФЗ ст. 6 ч. 1 | ст. 5 ч. 2"
    assert first["requirements"] == ["ru:demo-policy"]


@pytest.mark.parametrize(
    "cell, status, qualifier",
    [
        ("обязательно", "обязательно", ""),
        ("обязательно (сайт, веб-приложение)", "обязательно", "сайт, веб-приложение"),
        ("при условии: есть кабинет (B2C)", "при условии", "есть кабинет (B2C)"),
        ("рекомендуется (практика (суды); вывод)", "рекомендуется", "практика (суды); вывод"),
        ("рекомендуется. Норм нет", "рекомендуется", "Норм нет"),
        ("обязательно как требование акта КС. Это не норма", "обязательно", "как требование акта КС. Это не норма"),
        ("рекомендуется (a) и (b)", "рекомендуется", "(a) и (b)"),
    ],
)
def test_split_status(cell, status, qualifier):
    assert tpl.split_status(cell) == (status, qualifier)


@pytest.mark.parametrize("cell", ["", "желательно", "обязательность"])
def test_unknown_status_is_an_error(cell):
    with pytest.raises(tpl.TemplateError):
        tpl.split_status(cell)


N = "152-ФЗ ст. 9"  # a non-empty «Норма» cell


@pytest.mark.parametrize(
    "text, qualifier, norm, method",
    [
        # norm, practice, interpretation, inference: the markers of the first rounds
        ("Текст", "", N, "norm"),
        ("Данные выводятся на экран", "выведено судами", N, "norm"),
        ("Политика (трактовка)", "сайт", N, "interpretation"),
        ("Текст", "трактовка: запрета нет", N, "interpretation"),
        ("Текст", "инженерная практика; трактовка", N, "interpretation"),
        ("Текст", "инженерная практика; вывод из позиции суда", N, "practice"),
        ("Текст", "практика: дело N", N, "practice"),
        ("Текст", "вывод из признака «конкретное»", N, "inference"),
        ("Вывод карточки", "", N, "inference"),
        # «трактовк…», «инженерная практика» and «вывод» count in the «Норма» cell as well
        ("Текст", "", "152-ФЗ ст. 9; способ — трактовка", "interpretation"),
        ("Текст", "условие", "152-ФЗ ст. 9. Трактовка (medium)", "interpretation"),
        ("Текст", "", "ст. 5; журнал — инженерная практика", "practice"),
        ("Текст (журнал — инженерная практика)", "", "ст. 5", "practice"),
        ("Текст", "", "ст. 5; квалификация — вывод", "inference"),
        ("Текст", "", "Обзор судебной практики; выводы суда", "norm"),
        # platform: store and marketplace rules, «не закон»
        ("Правила магазинов: Apple, Google Play", "приложение в магазине", "Правила площадок", "platform"),
        ("Правила сторов: Apple 4.5.4", "", N, "platform"),
        ("Текст", "Это правило магазина, не закон", N, "platform"),
        ("Текст", "", "Правила площадок", "platform"),
        ("Текст", "условие", "Постановление КС; закон не менялся", "norm"),
        # interpretation: «не норма», «ориентир толкования», «ориентиры», FAQ, agency position
        ("Текст", "ориентир толкования, не норма", "Обзор ВС РФ п. 10", "interpretation"),
        ("Текст", "Обзор ВС 2022 — ориентиры, не нормы", N, "interpretation"),
        ("Текст", "это не норма РФ", N, "interpretation"),
        ("Текст", "позиция FAQ ФНС без реквизитов", N, "interpretation"),
        ("Текст", "позиции РКН нет, вопрос открыт", N, "interpretation"),
        ("Текст", "переносить позицию ФАС на ст. 8 нельзя", N, "interpretation"),
        ("Региональные позиции Роспотребнадзора по сертификатам", "", N, "interpretation"),
        ("Текст", "без позиции органа нельзя", N, "interpretation"),
        ("Текст", "позиция суда", N, "norm"),  # not an agency
        ("Позиция в списке товаров магазина, которые продаются онлайн", "РКН ведёт реестр", N, "norm"),  # far apart
        # these new markers are not searched in the «Норма» cell (it often names a side source)
        ("Текст", "запрет", "ЗоЗПП ст. 16 п. 1; Обзор ВС — ориентир толкования", "norm"),
        ("Текст", "", "Единые правила — не норма РФ; позиция ФАС", "norm"),
        # an empty «Норма» cell can never be a norm
        ("Текст", "условие", "", "practice"),
        ("Текст", "вывод из ст. 5", "", "inference"),
        ("Текст", "трактовка", "", "interpretation"),
        ("Правила сторов", "", "", "platform"),
        # precedence: platform > interpretation > practice > inference > norm
        ("Правила сторов", "трактовка", N, "platform"),
        ("Текст", "инженерная практика", "ст. 5 — трактовка", "interpretation"),
        ("Текст", "инженерная практика; ориентир толкования", N, "interpretation"),
        ("Текст", "вывод", "ст. 5; инженерная практика", "practice"),
    ],
)
def test_method_of(text, qualifier, norm, method):
    assert tpl.method_of(text, qualifier, norm) == method


def test_methods_lists_every_value():
    assert tpl.METHODS == ("norm", "practice", "interpretation", "inference", "platform")


def test_methods_of_synthetic_elements():
    rows = tpl.extract_elements(tpl.load_template(FORM))
    methods = {row["id"]: row["method"] for row in rows}
    assert methods == {
        "А1": "norm", "А2": "interpretation", "А3": "practice", "А4": "norm", "А5": "interpretation",
        "А6": "practice",
        "А7": "interpretation", "А10": "inference", "Б2": "norm", "Б3": "interpretation", "Б10": "practice",
    }
    assert element(rows, "А3")["norm"] == ""  # the dash cell: no norm, so no `norm` method


def test_mark_only_in_the_norm_cell_sets_the_method_and_keeps_the_status():
    rows = tpl.extract_elements(tpl.load_template(FORM))
    row = element(rows, "А7")
    assert "трактовка" in row["norm"] and "трактовк" not in row["text"] + row["qualifier"]
    assert row["method"] == "interpretation"
    mandatory = _template_with_rows(
        "| А1. Политика размещена | обязательно | 152-ФЗ ст. 18.1; достаточность ссылки — трактовка | [[a|A]] |",
        "| А2. Магазин требует экран | обязательно (приложение) | Правила площадок | [[a|A]] |",
        "| А3. Запрет в законе | обязательно | ЗоЗПП ст. 16 п. 1 | [[a|A]] |",
        "| А4. Запрет без нормы | обязательно | — | [[a|A]] |",
    )
    rows = {r["id"]: (r["status"], r["method"]) for r in tpl.extract_elements(mandatory)}
    assert rows == {
        "А1": ("обязательно", "interpretation"),
        "А2": ("обязательно", "platform"),
        "А3": ("обязательно", "norm"),
        "А4": ("обязательно", "practice"),
    }


def test_requirements_come_from_card_wikilinks():
    rows = tpl.extract_elements(tpl.load_template(FORM))
    assert element(rows, "Б2")["requirements"] == ["ru:demo-consent", "ru:demo-policy"]
    assert element(rows, "Б10")["requirements"] == ["ru:demo-consent"]  # listed twice, kept once
    assert element(rows, "А6")["requirements"] == []  # only a link to another template


def test_dash_norm_becomes_empty():
    assert element(tpl.extract_elements(tpl.load_template(FORM)), "А3")["norm"] == ""


def _template_with_rows(*rows):
    body = "\n".join(rows)
    section = f"| Элемент | Статус | Норма | Карточка |\n|---|---|---|---|\n{body}"
    return tpl.Template("x", {}, {"2. Обязательное содержание": section})


def test_element_without_id_is_an_error():
    with pytest.raises(tpl.TemplateError, match="without id"):
        tpl.extract_elements(_template_with_rows("| Без номера | обязательно | — | [[a|A]] |"))


def test_repeated_element_id_is_an_error():
    rows = ["| А1. Раз | обязательно | — | [[a|A]] |", "| А1. Два | обязательно | — | [[a|A]] |"]
    with pytest.raises(tpl.TemplateError, match="repeated"):
        tpl.extract_elements(_template_with_rows(*rows))


# ------------------------------------------------------------------ placeholders and forbidden clauses


def test_placeholders_take_hints_from_the_table_and_find_the_rest_in_the_text():
    found = tpl.extract_placeholders(tpl.load_template(FORM))
    assert sorted(found) == [
        "ВЕРСИЯ", "ДАТА_РЕДАКЦИИ", "ИНН", "НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА", "ПЕРЕЧЕНЬ_ДАННЫХ", "ССЫЛКА_НА_ПОЛИТИКУ",
    ]
    assert found["ИНН"] == {"hint": "Реквизиты по статусу", "templates": ["demo-form"]}
    assert found["НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА"]["hint"] == "Реквизиты по статусу"  # one row lists both names
    assert found["ПЕРЕЧЕНЬ_ДАННЫХ"]["hint"] == "Поля формы"
    assert found["ССЫЛКА_НА_ПОЛИТИКУ"]["hint"] == ""  # empty cell
    assert found["ВЕРСИЯ"]["hint"] == ""  # not in the table


def test_merged_placeholders_keep_first_hint_and_all_templates():
    merged = tpl.merge_placeholders(
        [tpl.extract_placeholders(tpl.load_template(FORM)), tpl.extract_placeholders(tpl.load_template(OTHER))]
    )
    assert list(merged) == sorted(merged)
    assert merged["ИНН"] == {"hint": "Реквизиты по статусу", "templates": ["demo-form", "demo-other"]}
    assert merged["ЦЕЛИ"] == {"hint": "Цели рассылки", "templates": ["demo-other"]}


def test_merge_takes_a_later_hint_when_the_first_is_empty():
    first = {"X": {"hint": "", "templates": ["a"]}}
    second = {"X": {"hint": "Позже", "templates": ["b"]}}
    assert tpl.merge_placeholders([first, second]) == {"X": {"hint": "Позже", "templates": ["a", "b"]}}


def test_forbidden_clauses_come_from_tables_outside_fences():
    rows = tpl.extract_forbidden(tpl.load_template(FORM))
    assert rows == [
        {
            "template": "demo-form",
            "pattern_text": "«Продавец вправе отменить заказ», «цена может быть изменена»",
            "violates": "пп. 1 п. 2 ст. 16",
            "severity": "violation",
        },
        {
            "template": "demo-form", "pattern_text": "«Споры только по месту продавца»", "violates": "пп. 2",
            "severity": "violation",
        },
        {
            "template": "demo-form",
            "pattern_text": "«Скидка при оплате через СБП»",
            "violates": "Зона риска, а не бесспорное нарушение: раздел 6.7",
            "severity": "risk",
        },
    ]
    assert tpl.extract_forbidden(tpl.load_template(OTHER)) == []


@pytest.mark.parametrize(
    "violates, severity",
    [
        ("пп. 4, 9", "violation"),
        ("зона риска, а не бесспорное нарушение", "risk"),
        ("Зоне риска относится", "risk"),
        ("в зоне риска: разница между способами", "risk"),
        ("пп. 7; ст. 16.1 п. 4", "violation"),
        ("риск претензий", "violation"),
    ],
)
def test_forbidden_severity(violates, severity):
    section = f"| Формулировка | Что нарушает |\n|---|---|\n| «текст» | {violates} |"
    t = tpl.Template("x", {}, {"3. Шаблон текста": section})
    assert tpl.extract_forbidden(t)[0]["severity"] == severity


# ------------------------------------------------------------------ cleaning and rendering


def test_clean_rewrites_links_outside_fences_and_keeps_fences_verbatim():
    md = (
        "Смотри [[demo-consent|карточку]] ([карточка](../concepts/demo-consent.md)) и [Политика](demo-policy.md).\n"
        "```markdown\n"
        "Подробнее в [Политике]({{ССЫЛКА}}) и [тексте](/privacy), [[unresolved]], discovery.\n"
        "```\n"
        "Конец, см. discovery."
    )
    out = tpl.clean(md, make_ctx())
    assert out.split("\n")[0] == "Смотри [карточку](../../cards/demo-consent.md) и [Политика](../../cards/demo-policy.md)."
    assert [text for fenced, text in tpl.segments(out) if fenced] == [text for fenced, text in tpl.segments(md) if fenced]
    assert out.split("\n")[-1] == "Конец, см. предварительный поиск."


def test_render_text_has_sections_three_and_four_only():
    t = tpl.load_template(FORM)
    out = tpl.render_text(t, make_ctx())
    assert out.startswith("# Шаблон: демо-форма\n")
    headings = [h for level, h in tpl.outline(out) if level == 2]
    assert headings == ["3. Шаблон текста", "4. Как разместить на сайте или в приложении"]
    assert "Обозначения вида А4 или Б2" in out and "`demo-form`" in out
    assert tpl.fenced_blocks(out) == tpl.fenced_blocks(t.section_text(3))
    assert "See Also" not in out and "Sources" not in out
    assert "[Согласие]" not in out  # a bare link to a concept file is reduced to its text
    assert "[Политика](../../cards/demo-policy.md)" in out
    assert "[[" not in "\n".join(t for fenced, t in tpl.segments(out) if not fenced)


def test_render_meta_has_sections_one_five_six_and_frontmatter():
    t = tpl.load_template(FORM)
    out = tpl.render_meta(t, make_ctx())
    lines = out.split("\n")
    assert lines[0] == "---" and lines[1] == "template: demo-form"
    closing = lines.index("---", 1)
    assert lines[2:closing] == [
        'summary: "Демонстрационный шаблон формы с согласием."',
        "updated: 2026-04-10",
        "verified: 2026-04-11",
        "confidence: medium",
        "volatility: hot",
    ]
    headings = [h for level, h in tpl.outline(out) if level == 2]
    assert headings == ["1. Назначение и когда нужен", "5. Что заполнить и проверить владельцу", "6. Спорные места и варианты"]
    assert "[Согласие на обработку](../../cards/demo-consent.md)" in out
    assert "[Шаблон: рассылка](../demo-other/text.md)" in out
    assert f"[закон]({RAW_URL})" in out
    assert "Хаб" in out and "demo-hub" not in out
    assert "raw/" not in out and "../concepts" not in out and "../topics" not in out
    assert "`{{ИНН}}`" in out


def github_anchor(title):
    kept = [
        ch for ch in re.sub(r"`([^`]*)`", r"\1", title).lower()
        if ch.isalnum() or ch in "-_ " or unicodedata.category(ch).startswith("M")
    ]
    return "".join(kept).replace(" ", "-")


def test_toc_added_only_to_long_files_and_its_links_resolve():
    t = tpl.load_template(FORM)
    short = tpl.render_text(t, make_ctx())
    assert "## Оглавление" not in short

    long_text = "\n".join(f"- пункт {i}" for i in range(120))
    long_t = tpl.Template("long", {}, {"3. Шаблон текста": f"### 3.1. Блок\n\n{long_text}\n\n### 3.2. Ещё", "4. Размещение": "x"})
    out = tpl.render_text(long_t, make_ctx())
    assert len(out.splitlines()) > tpl.TOC_MIN_LINES
    lines = out.splitlines()
    assert "## Оглавление" in lines[:15]
    links = re.findall(r"\]\(#([^)]+)\)", out)
    anchors = {github_anchor(title) for _, title in tpl.outline(out)}
    assert len(links) == 4 and set(links) <= anchors
    assert links[0] == "3-шаблон-текста" and links[1] == "31-блок"


def test_toc_threshold_counts_lines_the_way_the_repo_does():
    """A file of exactly TOC_MIN_LINES lines has no table of contents, one line more needs it."""

    def render(filler: int) -> str:
        body = "\n".join(f"- пункт {i}" for i in range(filler))
        return tpl.render_text(tpl.Template("x", {}, {"3. Шаблон текста": body}), make_ctx())

    first_long = next(k for k in range(1, 200) if "## Оглавление" in render(k))
    assert "## Оглавление" not in render(first_long - 1)
    assert len(render(first_long - 1).splitlines()) == tpl.TOC_MIN_LINES
    assert len(render(first_long).splitlines()) > tpl.TOC_MIN_LINES


def test_anchor_matches_github_rules():
    assert tpl.anchor("3.1. Блок «если используете»: ключ") == "31-блок-если-используете-ключ"
    assert tpl.anchor("`code` Title") == "code-title"


# ------------------------------------------------------------------ build


def test_build_templates_writes_files_and_indexes(topic, tmp_path):
    out = tmp_path / "ru"
    facts = tpl.build_templates(topic, out, make_ctx())
    assert facts["templates"] == 2 and facts["skipped"] == ["not-a-template"]
    assert facts["tables"] == 3 and facts["elements"] == 12
    assert facts["statuses"] == {"обязательно": 5, "при условии": 2, "рекомендуется": 5}
    assert facts["methods"] == {"norm": 4, "practice": 3, "interpretation": 4, "inference": 1, "platform": 0}
    assert facts["placeholders"] == 7 and facts["forbidden"] == 3
    assert facts["placeholders_without_hint"] == ["ВЕРСИЯ", "ДАТА_РЕДАКЦИИ", "ССЫЛКА_НА_ПОЛИТИКУ"]
    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert written == [
        "elements.json",
        "forbidden-clauses.json",
        "placeholders.json",
        "templates/README.md",
        "templates/demo-form/meta.md",
        "templates/demo-form/text.md",
        "templates/demo-other/meta.md",
        "templates/demo-other/text.md",
    ]
    assert sorted(tpl.generated_paths(out)) == written
    elements = json.loads((out / "elements.json").read_text(encoding="utf-8"))
    assert [r["template"] for r in elements] == ["demo-form"] * 11 + ["demo-other"]
    placeholders = json.loads((out / "placeholders.json").read_text(encoding="utf-8"))
    assert placeholders["ИНН"]["templates"] == ["demo-form", "demo-other"]
    forbidden = json.loads((out / "forbidden-clauses.json").read_text(encoding="utf-8"))
    assert [r["severity"] for r in forbidden] == ["violation", "violation", "risk"]
    for path in out.rglob("*"):
        if path.is_file():  # fenced blocks are copied as they are, so they are not searched
            outside = "\n".join(t for fenced, t in tpl.segments(path.read_text(encoding="utf-8")) if not fenced)
            assert not [bad for bad in FORBIDDEN_IN_PACK if bad in outside], path


def test_text_files_link_to_other_templates_and_cards_relative_to_their_folder(topic, tmp_path):
    out = tmp_path / "ru"
    tpl.build_templates(topic, out, make_ctx())
    meta = (out / "templates" / "demo-other" / "meta.md").read_text(encoding="utf-8")
    assert "[Шаблон: демо-форма](../demo-form/text.md)" in meta
    text = (out / "templates" / "demo-form" / "text.md").read_text(encoding="utf-8")
    assert "(../../cards/demo-policy.md)" in text


def test_build_is_deterministic(topic, tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    tpl.build_templates(topic, first, make_ctx())
    tpl.build_templates(topic, second, make_ctx())
    names = sorted(p.relative_to(first).as_posix() for p in first.rglob("*") if p.is_file())
    assert names == sorted(p.relative_to(second).as_posix() for p in second.rglob("*") if p.is_file())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_build_removes_files_of_templates_that_disappeared(topic, tmp_path):
    out = tmp_path / "ru"
    tpl.build_templates(topic, out, make_ctx())
    (topic / "wiki" / "references" / "shablon-demo-other.md").unlink()
    tpl.build_templates(topic, out, make_ctx(template_slugs={"demo-form"}))
    assert not (out / "templates" / "demo-other").exists()  # the folder goes with its files
    assert (out / "templates" / "demo-form" / "text.md").is_file()
    assert "demo-other" not in (out / "elements.json").read_text(encoding="utf-8")


def test_build_writes_nothing_without_templates_and_clears_old_files(topic, tmp_path):
    out = tmp_path / "ru"
    tpl.build_templates(topic, out, make_ctx())
    (out / "JURISDICTION.md").write_text("manual", encoding="utf-8")
    for name in ("shablon-demo-form.md", "shablon-demo-other.md"):
        (topic / "wiki" / "references" / name).unlink()
    facts = tpl.build_templates(topic, out, make_ctx())
    assert facts["templates"] == 0 and facts["skipped"] == ["not-a-template"] and facts["elements"] == 0
    assert tpl.generated_paths(out) == set()
    assert not (out / "templates").exists()
    assert (out / "JURISDICTION.md").read_text(encoding="utf-8") == "manual"  # files that are not ours stay
    fresh = tmp_path / "fresh"
    tpl.build_templates(topic, fresh, make_ctx())
    assert not fresh.exists()


def test_build_rejects_an_element_that_cites_an_unknown_card(topic, tmp_path):
    with pytest.raises(tpl.TemplateError, match="demo-policy"):
        tpl.build_templates(topic, tmp_path / "ru", make_ctx(card_slugs={"demo-consent"}))


def test_json_rows_are_one_per_line(topic, tmp_path):
    out = tmp_path / "ru"
    tpl.build_templates(topic, out, make_ctx())
    lines = (out / "elements.json").read_text(encoding="utf-8").split("\n")
    assert lines[0] == "[" and lines[-2] == "]" and lines[-1] == ""
    assert all(json.loads(line.rstrip(",")) for line in lines[1:-2])
    assert (out / "placeholders.json").read_text(encoding="utf-8").startswith("{\n\"ВЕРСИЯ\":{")


def test_readme_indexes_templates_and_lists_placeholders_without_hint(topic, tmp_path):
    out = tmp_path / "ru"
    tpl.build_templates(topic, out, make_ctx())
    readme = (out / "templates" / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Шаблоны документов (ru)\n")
    assert "### demo-form" in readme and "### demo-other" in readme
    assert "[text.md](demo-form/text.md)" in readme
    assert "- demo-form: `{{ВЕРСИЯ}}`, `{{ДАТА_РЕДАКЦИИ}}`, `{{ССЫЛКА_НА_ПОЛИТИКУ}}`" in readme
    assert "Всего 3 из 7" in readme
    assert "Блоков markdown в `text.md`: 3." in readme


# ------------------------------------------------------------------ integration tests

needs_wiki = pytest.mark.skipif(not (WIKI and BUILD_REFS), reason=SKIP_REASON)

EXPECTED_TEMPLATES = [
    "cookie-banner-i-uvedomlenie", "oferta-uslugi-i-podpiska", "politika-obrabotki-pdn",
    "publichnaya-oferta-tovary", "soglasie-na-obrabotku-pdn", "soglasie-na-rasprostranenie-pdn",
    "soglasie-na-rassylku", "svedeniya-o-prodavce-i-vladelce-sayta", "usloviya-vozvrata-i-obmena",
]


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """The pack of the real topic, built by the CLI (cards, requirements.jsonl and the template files)."""
    import build_knowledge  # imported here: the unit tests above do not need the card generator

    topic = Path(WIKI)
    out = tmp_path_factory.mktemp("pack") / "ru"
    assert build_knowledge.main(["--wiki", str(topic), "--build-refs", BUILD_REFS, "--out", str(out)]) == 0
    return {"topic": topic, "out": out, "templates": tpl.load_templates(topic)}


def read_json(real, name):
    return json.loads((real["out"] / name).read_text(encoding="utf-8"))


@needs_wiki
def test_nine_templates_and_fifty_one_tables(real):
    assert [t.slug for t in real["templates"]] == EXPECTED_TEMPLATES
    assert sorted(p.name for p in (real["out"] / "templates").iterdir() if p.is_dir()) == EXPECTED_TEMPLATES
    assert sum(len(tpl.element_tables(t)) for t in real["templates"]) == 51


@needs_wiki
def test_elements_count_and_status_split(real):
    rows = read_json(real, "elements.json")
    assert len(rows) == 322
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in tpl.STATUSES}
    assert counts == {"обязательно": 109, "при условии": 118, "рекомендуется": 95}


@needs_wiki
def test_element_rows_are_well_formed_and_sorted(real):
    rows = read_json(real, "elements.json")
    assert {r["template"] for r in rows} == set(EXPECTED_TEMPLATES)
    for row in rows:
        assert list(row) == ["template", "id", "section", "text", "status", "qualifier", "method", "norm", "requirements"]
        assert re.fullmatch(r"[А-К]\d+", row["id"]) and row["id"][0] == row["section"]
        assert row["status"] in tpl.STATUSES and row["method"] in tpl.METHODS
        assert row["text"] and "\n" not in row["text"] and "[[" not in row["text"] + row["norm"]
    keys = [(r["template"], tpl.SECTION_LETTERS.index(r["section"]), int(r["id"][1:])) for r in rows]
    assert keys == sorted(keys)
    assert len({(r["template"], r["id"]) for r in rows}) == len(rows)


@needs_wiki
def test_consent_element_a4_is_an_interpretation(real):
    row = next(r for r in read_json(real, "elements.json") if r["template"] == "soglasie-na-obrabotku-pdn" and r["id"] == "А4")
    assert row["status"] == "обязательно" and row["method"] == "interpretation"
    assert row["requirements"] == ["ru:politika-obrabotki-pdn"]


@needs_wiki
def test_marks_in_the_norm_cell_make_a_mandatory_element_an_interpretation(real):
    rows = {(r["template"], r["id"]): r for r in read_json(real, "elements.json")}
    for key in (("politika-obrabotki-pdn", "А2"), ("politika-obrabotki-pdn", "Б15")):
        assert rows[key]["status"] == "обязательно" and rows[key]["method"] == "interpretation", key
        assert "трактовк" in rows[key]["norm"] and "трактовк" not in rows[key]["text"] + rows[key]["qualifier"]


# Literal counts: a change of the method rules shows up here and has to be reviewed, not just re-run.
METHODS_TOTAL = {"norm": 202, "practice": 47, "interpretation": 55, "inference": 16, "platform": 2}
METHODS_AMONG_MANDATORY = {"norm": 92, "practice": 1, "interpretation": 11, "inference": 5, "platform": 0}


@needs_wiki
def test_method_counts_are_pinned(real):
    rows = read_json(real, "elements.json")
    assert {m: sum(1 for r in rows if r["method"] == m) for m in tpl.METHODS} == METHODS_TOTAL
    mandatory = [r for r in rows if r["status"] == "обязательно"]
    assert {m: sum(1 for r in mandatory if r["method"] == m) for m in tpl.METHODS} == METHODS_AMONG_MANDATORY
    assert sum(METHODS_TOTAL.values()) == 322 and sum(METHODS_AMONG_MANDATORY.values()) == 109


@needs_wiki
def test_known_rows_have_the_expected_method(real):
    rows = {(r["template"], r["id"]): r["method"] for r in read_json(real, "elements.json")}
    assert rows[("cookie-banner-i-uvedomlenie", "Д2")] == "platform"  # store rules, not law
    assert rows[("soglasie-na-rassylku", "В4")] == "platform"
    assert rows[("oferta-uslugi-i-podpiska", "Г3")] == "interpretation"  # «ориентир толкования, не норма»
    assert rows[("oferta-uslugi-i-podpiska", "К1")] == "interpretation"  # «ориентиры, не нормы»
    assert rows[("publichnaya-oferta-tovary", "В7")] == "interpretation"  # FAQ ФНС
    assert rows[("publichnaya-oferta-tovary", "Б10")] == "practice"  # no norm in the cell
    assert rows[("cookie-banner-i-uvedomlenie", "Г3")] == "practice"  # no norm in the cell
    assert rows[("publichnaya-oferta-tovary", "А4")] == "norm"  # a statute; the review is only a side source


@needs_wiki
def test_an_element_without_a_norm_is_never_a_norm(real):
    rows = read_json(real, "elements.json")
    assert [r["id"] for r in rows if not r["norm"] and r["method"] == "norm"] == []
    assert sum(1 for r in rows if not r["norm"]) == 29


@needs_wiki
def test_every_requirement_exists_in_requirements_jsonl(real):
    known = {
        json.loads(line)["id"]
        for line in (real["out"] / "requirements.jsonl").read_text(encoding="utf-8").splitlines()
    }
    used = {r for row in read_json(real, "elements.json") for r in row["requirements"]}
    assert used and used <= known, sorted(used - known)


@needs_wiki
def test_forty_eight_markdown_blocks_are_kept_byte_for_byte(real):
    total = 0
    for t in real["templates"]:
        source = tpl.fenced_blocks(t.section_text(3) + "\n" + t.section_text(4))
        text = (real["out"] / "templates" / t.slug / "text.md").read_text(encoding="utf-8")
        assert tpl.fenced_blocks(text) == source, t.slug
        total += sum(1 for info, _ in tpl.fenced_blocks(text) if info == "markdown")
    assert total == 48


@needs_wiki
def test_220_placeholders_and_hints(real):
    placeholders = read_json(real, "placeholders.json")
    assert len(placeholders) == 220 and list(placeholders) == sorted(placeholders)
    source = set()
    for t in real["templates"]:
        source |= set(re.findall(r"\{\{([A-ZА-ЯЁ0-9_]+)\}\}", "\n".join(t.sections.values())))
    assert set(placeholders) == source
    assert all(set(entry) == {"hint", "templates"} and entry["templates"] for entry in placeholders.values())
    without = sorted(name for name, entry in placeholders.items() if not entry["hint"])
    # Hints exist only for names the «Что вписать» tables list; the rest is named in templates/README.md.
    assert len(placeholders) - len(without) >= 0.9 * len(placeholders)
    readme = (real["out"] / "templates" / "README.md").read_text(encoding="utf-8")
    assert f"Всего {len(without)} из 220" in readme
    assert all(f"`{{{{{name}}}}}`" in readme for name in without)


@needs_wiki
def test_every_placeholder_in_the_shipped_text_is_indexed(real):
    placeholders = set(read_json(real, "placeholders.json"))
    for t in real["templates"]:
        for name in ("text.md", "meta.md"):
            text = (real["out"] / "templates" / t.slug / name).read_text(encoding="utf-8")
            assert set(re.findall(r"\{\{([A-ZА-ЯЁ0-9_]+)\}\}", text)) <= placeholders


@needs_wiki
def test_forbidden_clauses_are_not_empty(real):
    rows = read_json(real, "forbidden-clauses.json")
    keys = ["template", "pattern_text", "violates", "severity"]
    assert rows and all(list(r) == keys and all(r.values()) for r in rows)
    assert {r["template"] for r in rows} == {"publichnaya-oferta-tovary"}
    assert len(rows) == 11


@needs_wiki
def test_forbidden_clauses_mark_the_risk_zone(real):
    rows = read_json(real, "forbidden-clauses.json")
    risky = [r for r in rows if r["severity"] == "risk"]
    assert len(risky) == 1 and "СБП" in risky[0]["pattern_text"] and "зона риска" in risky[0]["violates"]
    assert sum(1 for r in rows if r["severity"] == "violation") == 10
    assert not [r for r in rows if r["severity"] == "violation" and "зона риска" in r["violates"].lower()]


# The markers the card tests look for in the whole pack; the template files must be free of them too.
PRIVATE_MARKERS = [
    r"\[\[", r"raw/", r"wiki/", r"\.\./topics", r"\.\./references", r"/Us" + r"ers/", r"(?i)llm" + r"-wiki",
    r"\bP\d{1,2}\b", r"(?i)discovery", r"(?i)\bхаб(?:а|е|у|ом)?\b", r"(?i)(?<![a-z])wiki(?![a-z])",
    r"(?i)schema\.md", r"(?i)ingest", r"(?i)path report", r"(?i)modern-web-app-development",
    r"(?i)\bпут[иь]\s+P\d", r"wiki/concepts", r"wiki/references", r"\]\(\.\./concepts",
]


@needs_wiki
def test_generated_files_contain_no_private_markers(real):
    paths = sorted(real["out"] / rel for rel in tpl.generated_paths(real["out"]))
    assert len(paths) == 9 * 2 + 1 + 3
    for path in paths:
        text = path.read_text(encoding="utf-8")
        found = [marker for marker in PRIVATE_MARKERS if re.search(marker, text)]
        assert not found, f"{path.name}: {found}"


@needs_wiki
def test_links_in_generated_files_resolve(real):
    out = real["out"]
    for path in (out / "templates").rglob("*.md"):
        for fenced, text in tpl.segments(path.read_text(encoding="utf-8")):
            if fenced:
                continue
            for target in re.findall(r"\]\(([^)\s]+)\)", text):
                if target.startswith(("http://", "https://", "#")):
                    continue
                assert (path.parent / target).is_file(), f"{path.relative_to(out)}: {target}"


@needs_wiki
def test_long_files_start_with_a_table_of_contents(real):
    for path in (real["out"] / "templates").rglob("*.md"):
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > tpl.TOC_MIN_LINES:
            assert "## Оглавление" in lines[:15], path


@needs_wiki
def test_build_is_deterministic_on_the_real_topic(real, tmp_path):
    cards = {p.stem for p in (real["topic"] / "wiki" / "concepts").glob("*.md") if p.name != "_index.md"}
    ctx = LinkCtx(card_slugs=cards, template_slugs=set(), raw_urls=raw_url_map(real["topic"]))
    again = tmp_path / "ru"
    tpl.build_templates(real["topic"], again, ctx)
    names = sorted(tpl.generated_paths(again))
    assert names == sorted(tpl.generated_paths(real["out"]))
    for name in names:
        assert (again / name).read_bytes() == (real["out"] / name).read_bytes(), name


@needs_wiki
def test_cli_check_covers_the_template_files(real):
    import build_knowledge

    args = ["--wiki", str(real["topic"]), "--build-refs", BUILD_REFS, "--out", str(real["out"]), "--check"]
    assert build_knowledge.main(args) == 0
    elements = real["out"] / "elements.json"
    original = elements.read_bytes()
    try:
        elements.write_bytes(original + b" ")
        assert build_knowledge.main(args) == 1
    finally:
        elements.write_bytes(original)
    assert build_knowledge.main(args) == 0
