"""Unit tests for kb.dates (effective dates from the legal-basis table)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.dates import norm_dates  # noqa: E402


def test_norm_dates_bold_and_missing():
    section = (
        "| Норма | Содержание | Редакция и вступление в силу |\n"
        "|---|---|---|\n"
        "| Тест-ФЗ ст. 1 ч. 1 | основание | ред. 1-ФЗ, **с 01.09.2025** |\n"
        "| Тест-ФЗ ст. 2 | срок | дата не указана; снято 2026-01-01 |\n"
        "| Тест-ФЗ ст. 3 | форма |  |\n"
        "| Тест-ФЗ ст. 4 | срок | **с 01.03.2026**; изменения — с 01.09.2026 |\n"
        "| Тест-ФЗ ст. 5 | период | с 01.03.2022 до 01.03.2028 (п. 4) |\n"
        "| Тест-ФЗ ст. 6 | редакция | введена 42-ФЗ от 08.03.2015 |\n"
        "\n"
        "Официальные URL:\n\n- Тест-ФЗ: http://example.gov/doc/1\n"
    )
    assert norm_dates(section) == [
        {"norm": "Тест-ФЗ ст. 1 ч. 1", "from": "2025-09-01"},
        {"norm": "Тест-ФЗ ст. 2", "from": None},
        {"norm": "Тест-ФЗ ст. 3", "from": None},
        {"norm": "Тест-ФЗ ст. 4", "from": "2026-09-01"},
        {"norm": "Тест-ФЗ ст. 5", "from": "2022-03-01"},
        {"norm": "Тест-ФЗ ст. 6", "from": None},
    ]


def test_norm_dates_wikilink_pipe_does_not_split_cells():
    section = (
        "| Норма | Содержание | Редакция и вступление в силу |\n"
        "|---|---|---|\n"
        "| КоАП ст. 1 | ответственность, см. [[karta|карту]] ([Карта](karta.md)) | с 01.03.2027 |\n"
    )
    assert norm_dates(section) == [{"norm": "КоАП ст. 1", "from": "2027-03-01"}]


def test_norm_dates_store_policy_table_and_invalid_dates():
    section = (
        "| Документ | Содержание | Редакция и дата |\n"
        "|---|---|---|\n"
        "| Store Policy — Payments | правила | дата не указана; снято 2026-09-30 |\n"
        "| Приказ № 1 | порядок | с 31.02.2025 |\n"
    )
    assert norm_dates(section) == [
        {"norm": "Store Policy — Payments", "from": None},
        {"norm": "Приказ № 1", "from": None},
    ]


def test_norm_dates_without_table_is_empty():
    assert norm_dates("Просто текст без таблицы.") == []
    assert norm_dates("") == []


def test_norm_dates_strips_markdown_in_norm_name():
    section = (
        "| Норма | Содержание | Редакция и вступление в силу |\n"
        "|---|---|---|\n"
        "| **ГК** ст. 1 `п. 2` | x | с 01.01.2020 |\n"
    )
    assert norm_dates(section) == [{"norm": "ГК ст. 1 п. 2", "from": "2020-01-01"}]
