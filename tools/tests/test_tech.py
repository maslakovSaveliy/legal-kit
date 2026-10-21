"""Unit tests for kb.tech (technical-manifestation bullets)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from kb.tech import cannot_check_items, classify_tech, compact, gate_kind  # noqa: E402


def kinds(section):
    return [item["kind"] for item in classify_tech(section)]


def test_tech_kinds():
    section = (
        "- Нормативный пункт без оговорки.\n"
        "- Ведение журнала (инженерная практика — закон формат не задаёт).\n"
        "- Кнопка без «продолжая» (трактовка ст. 9).\n"
        "- Срок хранения (вывод из ч. 2).\n"
        "- Слово выводится из текста, но не как оговорка.\n"
    )
    assert kinds(section) == ["norm", "practice", "interpretation", "inference", "norm"]


def test_tech_lead_in_sets_default_kind():
    section = (
        "Прямо требуются законом:\n\n"
        "- Блок контактов.\n"
        "- Форма жалобы.\n\n"
        "Инженерная практика:\n\n"
        "- Журнал уведомлений.\n"
        "- Выгрузка статистики (трактовка).\n"
    )
    assert kinds(section) == ["norm", "norm", "practice", "interpretation"]
    # An explicit «прямо из закона» lead-in switches back from practice to norm.
    back = "Инженерная практика:\n\n- Журнал.\n\nПрямо из закона следует:\n\n- Блок контактов.\n"
    assert kinds(back) == ["practice", "norm"]


def test_tech_parenthesised_lead_in_marks_whole_list():
    section = "(инженерная практика, если не указано иное)\n\n- Первый.\n- Второй.\n"
    assert kinds(section) == ["practice", "practice"]


def test_tech_sentence_level_qualifier_outside_parentheses():
    section = (
        "- **Журнал.** Ведётся без изменений. Инженерная практика: хранить версии.\n"
        "- **Кошелёк:** вывод на внешний кошелёк возможен после теста.\n"
        "- Автопереключение карты рискованно — это вывод, а не норма.\n"
    )
    assert kinds(section) == ["practice", "norm", "inference"]


def test_tech_nested_bullets_merge_into_parent_with_strictest_marker():
    section = (
        "- **Форма:**\n"
        "  - поле e-mail;\n"
        "  - поле URL (инженерная практика).\n"
        "- Второй пункт.\n"
    )
    items = classify_tech(section)
    assert [i["kind"] for i in items] == ["practice", "norm"]
    assert "поле e-mail" in items[0]["text"]


def test_tech_indented_continuation_belongs_to_bullet():
    section = "- Журнал защищён от изменения.\n  Это инженерная практика.\n"
    items = classify_tech(section)
    assert len(items) == 1 and items[0]["kind"] == "practice"


def test_tech_text_limited_and_plain():
    long_bullet = "- **Заголовок.** " + "слово " * 80 + "[[a|ссылка]] ([A](a.md))\n"
    items = classify_tech(long_bullet)
    assert len(items) == 1
    assert len(items[0]["text"]) <= 200
    assert "**" not in items[0]["text"] and "[[" not in items[0]["text"]
    assert items[0]["text"].endswith("…")


def test_tech_without_bullets_falls_back_to_paragraphs_and_skips_tables():
    section = (
        "Степень вреда определяется по функциям. Это трактовка.\n\n"
        "| Функция | Степень |\n|---|---|\n| Форма | средняя |\n\n"
        "Инженерная практика: вести перечень функций.\n"
    )
    assert kinds(section) == ["interpretation", "practice"]


def test_compact_respects_limit_and_prefers_sentence_boundary():
    text = "Первое предложение полностью. " + "Длинное продолжение " * 20
    out = compact(text, 60)
    assert len(out) <= 60
    assert out == "Первое предложение полностью."
    assert compact("коротко", 60) == "коротко"
    word_cut = compact("слово " * 40, 30)
    assert len(word_cut) <= 30 and word_cut.endswith("…")


def test_cannot_check_items_plain_and_limited():
    section = (
        "- Опубликованный текст согласия на **проде**.\n"
        "- Журнал согласий: [[a|см. карточку]] ([A](a.md)) " + "и так далее " * 30 + "\n"
    )
    items = cannot_check_items(section)
    assert items[0] == "Опубликованный текст согласия на проде."
    assert len(items) == 2 and all(len(i) <= 200 for i in items)
    assert "[[" not in items[1]


def test_compact_drops_trailing_separators():
    assert compact("StoreKit для покупок;", 60) == "StoreKit для покупок"
    assert compact("Заголовок:", 60) == "Заголовок"


def test_authority_positions_and_market_practice_are_not_norms():
    section = (
        "- Знак по рекомендациям РКН 2012 г. Это позиция органа, закон этого не требует.\n"
        "- Возврат после отказа (позиция Роспотребнадзора) и чек.\n"
        "- Пара чеков «предоплата» и «полный расчёт» (позиция ФНС).\n"
        "- Поиск по реестру образцов (практика; доступность реестра не проверялась).\n"
        "- Так принято по практике рынка.\n"
        "- Смежное правило магазина приложений о запрете.\n"
        "- ЦБ рекомендует час для ответа.\n"
        "- Классификация по п. 2 не требуется, но нужен процесс для 18+.\n"
        "- Цена позиции не зависит от способа оплаты.\n"
        "- Отдельная страница под это не нужна: норма её не требует.\n"
    )
    assert kinds(section) == [
        "interpretation", "interpretation", "interpretation", "practice", "practice",
        "platform", "interpretation", "norm", "norm", "interpretation",
    ]


def test_negated_norm_lead_in_does_not_switch_back_to_norm():
    cases = [
        "Инженерная практика:\n\n- Журнал.\n\nНе требуются законом, но полезны:\n\n- Экран.\n",
        "Инженерная практика:\n\n- Журнал.\n\nПрямо из закона не следует, но стоит сделать:\n\n- Экран.\n",
        "Инженерная практика:\n\n- Журнал.\n\nПрямо требуются законом (нет, не требуются):\n\n- Экран.\n",
    ]
    for section in cases:
        assert kinds(section) == ["practice", "practice"], section


@pytest.mark.parametrize(
    "source_kind,expected",
    [
        (None, ["norm", "practice", "interpretation", "inference"]),
        ("law", ["norm", "practice", "interpretation", "inference"]),
        ("bylaw", ["norm", "practice", "interpretation", "inference"]),
        ("regulator", ["interpretation", "practice", "interpretation", "inference"]),
        ("court", ["interpretation", "practice", "interpretation", "inference"]),
        ("standard", ["practice", "practice", "interpretation", "inference"]),
        ("engineering", ["practice", "practice", "interpretation", "inference"]),
        ("store-policy", ["platform"] * 4),
        ("", ["interpretation", "practice", "interpretation", "inference"]),
        ("unknown", ["interpretation", "practice", "interpretation", "inference"]),
    ],
)
def test_kinds_are_capped_by_card_source_kind(source_kind, expected):
    section = (
        "- Нормативный пункт.\n"
        "- Журнал (инженерная практика).\n"
        "- Кнопка (трактовка ст. 9).\n"
        "- Срок (вывод из ч. 2).\n"
    )
    assert [i["kind"] for i in classify_tech(section, source_kind=source_kind)] == expected


def test_gate_kind_only_demotes_norm():
    assert gate_kind("inference", "court") == "inference"
    assert gate_kind("norm", "court") == "interpretation"
    assert gate_kind("platform", "law") == "platform"
    assert gate_kind("practice", "store-policy") == "platform"


def test_qualifier_clause_survives_shortening():
    head = "Реестр операций (ст. 148 п. 5): журнал транзакций с признаками места реализации и стоимостью, " * 2
    section = "- " + head + "Инженерная практика: хранить его неизменяемым и выгружаемым по периодам.\n"
    text = classify_tech(section)[0]["text"]
    assert len(text) <= 200
    assert text.endswith("Инженерная практика: хранить его неизменяемым и выгружаемым по периодам.")
    assert "…" in text

    parenthesised = "- Очень длинное начало пункта " * 6 + "(инженерная практика — закон формат не задаёт) и хвост " * 2 + "\n"
    result = classify_tech(parenthesised)[0]
    assert result["kind"] == "practice" and len(result["text"]) <= 200
    assert "(инженерная практика — закон формат не задаёт)" in result["text"]


def test_compact_keeps_a_clause_that_fits_before_the_cut():
    text = "Первая часть (трактовка ст. 9) и очень длинное продолжение " + "слово " * 40
    out = compact(text, 80, keep=(12, 30))
    assert len(out) <= 80 and "(трактовка ст. 9)" in out


def test_court_and_regulator_guidance_is_not_a_norm():
    section = (
        "- Знак в блоке выходных данных (подвал, страница «О редакции») — по рекомендациям для редакций.\n"
        "- Пересчёт по курсу ЦБ на дату получения (FAQ ФНС).\n"
        "- Цена без допа показывается явно (ВС, п. 12).\n"
        "- Нет условий «цена может быть изменена» (Обзор п. 4; ст. 16 п. 2).\n"
        "- Приём доказательств без чека (Пленум № 17 п. 43).\n"
        "- Латиница в SMS из дела ВС (п. 15 Обзора 2023).\n"
        "- Бремя доказывания по п. 78 Пленума № 10 на владельце.\n"
        "- Это позиция суда по спорам о доменах.\n"
        "- Ориентир — письмо ФНС о порядке выдачи чеков.\n"
        "- Письмо тем, кто уже купил товар.\n"
        "- Письменное согласие хранится отдельно.\n"
        "- Позиция товара в корзине указывается в чеке.\n"
    )
    assert kinds(section) == ["interpretation"] * 9 + ["norm"] * 3


def test_guidance_items_stay_non_norm_in_law_and_bylaw_cards():
    for source_kind in ("law", "bylaw"):
        items = classify_tech("- Приём доказательств без чека (Пленум № 17 п. 43).\n", source_kind=source_kind)
        assert items[0]["kind"] == "interpretation"


@pytest.mark.parametrize("abbreviation", ["ред", "прил", "ст", "ч", "п", "пп", "абз", "гл", "разд"])
def test_abbreviation_dots_are_not_sentence_ends(abbreviation):
    sample = f"Начало текста с длинной ссылкой на {abbreviation}. Продолжение " + "слово " * 30
    cut = compact(sample, 50)
    assert len(cut) <= 50
    assert not cut.rstrip("…").endswith(f"{abbreviation}."), cut


def test_cut_never_leaves_a_parenthesis_open():
    long_parenthesis = "Блокировка до согласия (Яндекс Метрика tag.js/ym(), Google gtag.js, контейнер GTM, пиксели VK) " * 3
    for limit in range(40, 140, 7):
        cut = compact(long_parenthesis, limit)
        assert len(cut) <= limit, (limit, cut)
        assert cut.count("(") == cut.count(")"), (limit, cut)
    # A cut inside a parenthesis that starts at the very beginning closes it after the ellipsis.
    closed = compact("(" + "слово " * 60 + ")", 50)
    assert len(closed) <= 50 and closed.endswith("…)") and closed.count("(") == closed.count(")")
    # A sentence end inside a parenthesis is not a cut point.
    inside = compact("Норма применяется (введена в ред. 5-ФЗ. Далее текст) " + "и ещё слова " * 20, 45)
    assert inside.count("(") == inside.count(")") and len(inside) <= 45
