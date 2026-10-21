"""Tests for the card generator: unit tests on a synthetic topic, integration tests on the real one.

Integration tests read the topic path from LEGAL_KIT_WIKI (and the table module from LEGAL_KIT_BUILD_REFS,
see wiki_env.py) and are skipped when it is unset.
"""

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import build_knowledge  # noqa: E402
from kb import emit_cards  # noqa: E402
from kb.dates import norm_dates  # noqa: E402
from kb.legacy import load_build_refs  # noqa: E402
from kb.links import LinkCtx, raw_url_map, unlink  # noqa: E402
from kb.parse import load_card, parse_frontmatter, split_sections  # noqa: E402
from kb.prose import scrub  # noqa: E402
from kb.tech import classify_tech  # noqa: E402
from wiki_env import BUILD_REFS, SKIP_REASON, WIKI  # noqa: E402

TOPIC = Path(__file__).resolve().parent / "fixtures" / "topic"
REFS = Path(__file__).resolve().parent / "fixtures" / "build_refs.py"
LAUNCH_DATE = "2026-10-17"

OBLIGATION = {"general", "conditional", "sectoral"}
SOURCE_KIND = {"law", "bylaw", "regulator", "court", "standard", "engineering", "store-policy"}
CONFIDENCE = {"high", "medium", "low"}
VOLATILITY = {"hot", "warm", "cold"}
SUBJECTS = {"ul", "ip", "npd", "foreign"}
MODELS = {"b2b", "b2c"}
PRODUCTS = {"site", "webapp", "ios", "android"}
TECH_KINDS = {"norm", "practice", "interpretation", "inference", "platform"}
REQUIRED_KEYS = [
    "id", "dir", "title", "summary", "trigger", "obligation", "source_kind", "legal_confidence",
    "volatility", "subjects", "models", "products", "acts", "effective_from", "norm_dates",
    "official_urls", "tech", "cannot_check", "templates", "card",
]
BASIS = "Правовое основание"
TECH = "Техническое проявление в продукте"
CANNOT = "Что нельзя проверить по репозиторию"


def fixture_card(slug="demo-consent"):
    return load_card(TOPIC / "wiki" / "concepts" / f"{slug}.md")


def fixture_brief(slug="demo-consent", templates=None):
    refs = load_build_refs(REFS)
    letter = emit_cards.dir_letter(refs.DIRS)[slug]
    return emit_cards.brief(fixture_card(slug), refs.TRIGGER[slug], letter, templates or {})


def fixture_ctx():
    return LinkCtx(
        card_slugs={"demo-consent", "demo-policy"},
        template_slugs={"demo-form"},
        raw_urls=raw_url_map(TOPIC),
        card_href=lambda slug: f"{slug}.md",
        template_href=lambda slug: f"../templates/{slug}/text.md",
    )


# ---------------------------------------------------------------- unit tests


def test_brief_size_limit():
    record = fixture_brief(templates={"demo-consent": ["demo-form"]})
    assert list(record) == REQUIRED_KEYS
    assert record["tech"] and all(len(t["text"]) <= 200 for t in record["tech"])
    assert record["cannot_check"] and all(len(t) <= 200 for t in record["cannot_check"])
    assert len(emit_cards.dumps(record)) <= 3000
    # Very long items cannot exceed the item limit, and the line stays within its budget.
    card = fixture_card()
    card.sections[TECH] = "\n".join(f"- пункт {'длинный ' * 100}{i}" for i in range(30))
    card.sections[CANNOT] = "\n".join(f"- проверка {'длинная ' * 100}{i}" for i in range(30))
    big = emit_cards.brief(card, "t", "A", {})
    assert all(len(t["text"]) <= 200 for t in big["tech"])
    assert all(len(t) <= 200 for t in big["cannot_check"])
    assert len(big["tech"]) >= 2 and len(big["cannot_check"]) >= 2
    assert len(emit_cards.dumps(big)) <= emit_cards.LINE_BUDGET


def test_brief_fields_from_fixture():
    record = fixture_brief(templates={"demo-consent": ["demo-form"]})
    assert record["id"] == "ru:demo-consent"
    assert record["dir"] == "A"
    assert record["trigger"] == "тестовая обработка данных"
    assert record["summary"] == "Тестовая карточка: основание, форма и срок. Вторая фраза, с запятой."
    assert record["obligation"] == "conditional"
    assert record["subjects"] == ["ul", "ip"]
    assert record["acts"] == ["Тест-ФЗ ст. 1 ч. 1, 2", "Тест-ПП № 5 п. 3"]
    assert record["effective_from"] == "2027-03-01"
    assert record["norm_dates"] == [
        {"norm": "Тест-ФЗ ст. 1 ч. 1", "from": "2025-09-01"},
        {"norm": "Тест-ФЗ ст. 2", "from": None},
        {"norm": "Тест-ПП № 5 п. 3", "from": "2027-03-01"},
    ]
    assert record["official_urls"] == [
        "http://example.gov/doc/1",
        "https://example.gov/doc/5",
        "https://example.gov/doc/5.pdf",
    ]
    assert [t["kind"] for t in record["tech"]] == ["norm", "practice", "interpretation", "inference"]
    assert record["cannot_check"] == [
        "Опубликованный текст согласия на проде.",
        "Журнал согласий и его выгрузка по запросу.",
    ]
    assert record["templates"] == ["demo-form"]
    assert record["card"] == "cards/demo-consent.md"


def test_urls_label_variants_in_legal_basis():
    record = fixture_brief("demo-policy")
    assert record["official_urls"] == ["https://example.gov/doc/18"]
    assert record["effective_from"] == "mixed"
    assert record["norm_dates"] == [{"norm": "Тест-ФЗ ст. 18.1", "from": "2022-09-01"}]


def test_brief_over_budget_keeps_whole_items_and_one_of_each_list():
    card = fixture_card()
    card.fm["summary"] = "Очень длинное резюме. " * 150
    record = emit_cards.brief(card, "t", "A", {})
    assert len(record["tech"]) == 1 and len(record["cannot_check"]) == 1
    assert record["tech"][0]["text"] == "Чекбокс согласия: отдельный, не отмеченный по умолчанию."
    assert record["summary"] == card.fm["summary"]
    # Nothing else gives way.
    assert len(record["acts"]) == 2 and len(record["norm_dates"]) == 3 and len(record["official_urls"]) == 3


def test_brief_never_trims_urls_acts_or_norms():
    card = fixture_card()
    long_act = "Приказ Минэкономразвития от 06.05.2026 № 368, Порядок п. 8, п. 9, п. 10 и приложение № 3 к нему"
    card.fm["acts"] = [long_act] + [f"Акт {i}" for i in range(12)]
    card.sections[BASIS] = (
        "| Норма | Содержание | Редакция и вступление в силу |\n|---|---|---|\n"
        f"| {long_act} | x | с 01.01.2027 |\n"
        + "".join(f"| Акт {i} | x | с 01.01.20{i + 10} |\n" for i in range(12))
        + "\nОфициальные URL:\n\n"
        + "".join(f"- Закон {i}: http://example.gov/doc/{i}\n" for i in range(30))
    )
    card.fm["summary"] = "Длинное резюме. " * 150
    record = emit_cards.brief(card, "t", "A", {})
    assert record["acts"][0] == long_act and len(record["acts"]) == 13
    assert record["norm_dates"][0] == {"norm": long_act, "from": "2027-01-01"} and len(record["norm_dates"]) == 13
    assert len(record["official_urls"]) == 30
    assert not any("…" in act for act in record["acts"])
    assert not any("…" in entry["norm"] for entry in record["norm_dates"])


def test_brief_caps_tech_kinds_by_source_kind():
    for source_kind, expected in (
        ("store-policy", {"platform"}),
        ("regulator", {"interpretation", "practice", "inference"}),
        ("standard", {"practice", "interpretation", "inference"}),
        ("law", {"norm", "practice", "interpretation", "inference"}),
    ):
        card = fixture_card()
        card.fm["source_kind"] = source_kind
        kinds = {t["kind"] for t in emit_cards.brief(card, "t", "A", {})["tech"]}
        assert kinds and kinds <= expected, source_kind
        if source_kind in ("store-policy", "law"):
            assert kinds == expected, source_kind


def test_brief_rewords_process_markers_in_frontmatter_values_and_items():
    card = fixture_card()
    card.fm["title"] = "Демо: хаб G"
    card.fm["summary"] = "Единственное место wiki с размерами (P27). См. [[demo-policy|политику]]."
    card.sections[CANNOT] = "- Не искалось в P16, discovery P8.\n"
    record = emit_cards.brief(card, "хаб K", "A", {})
    assert record["title"] == "Демо: направление G"
    assert record["summary"] == "Единственное место базы с размерами. См. политику."
    assert record["trigger"] == "направление K"
    assert record["cannot_check"] == ["Не искалось в базе, предварительный поиск."]


def test_official_urls_include_urls_that_raw_links_turn_into():
    card = fixture_card()
    card.sections[BASIS] = (
        "| Норма | Содержание | Редакция и вступление в силу |\n|---|---|---|\n"
        "| Ст. 1 | текст ([дополняющий raw](../../raw/articles/demo-official.md)) | с 01.01.2020 |\n"
        "| Ст. 2 | заметка ([raw](../../raw/notes/demo-manual.md)) | с 01.01.2021 |\n\n"
        "Официальные URL:\n\n- Закон: http://example.gov/law\n"
    )
    refs = load_build_refs(REFS)
    assert emit_cards.brief(card, "t", "A", {})["official_urls"] == ["http://example.gov/law"]
    with_context = emit_cards.brief(card, "t", "A", {}, fixture_ctx())["official_urls"]
    assert with_context == ["https://example.gov/doc/1", "http://example.gov/law"]
    assert refs.TRIGGER


def test_official_urls_rules():
    basis = (
        "| Норма | Содержание | Редакция и вступление в силу |\n|---|---|---|\n"
        "| Ст. 1 | страница: https://in-table.example/x | с 01.01.2020 |\n\n"
        "Официальные URL:\n\n"
        "- Закон (ИПС): http://example.gov/a?x=1&y=2.\n"
        "- Закон (PDF): http://example.gov/a?x=1&y=2 (копия: https://example.gov/b.pdf)\n"
        "- Акт (СудАкт): https://sudact.ru/regular/doc/abc/\n"
        "- Обзор: https://www.garant.ru/doc/1/\n\n"
        "Неофициальные копии: https://www.garant.ru/files/2.pdf\n"
        "Официальный URL: Закон о чём-то — http://example.gov/c\n"
    )
    assert emit_cards.official_urls(basis) == [
        "https://in-table.example/x",
        "http://example.gov/a?x=1&y=2",
        "https://example.gov/b.pdf",
        "http://example.gov/c",
    ]


def test_dumps_is_compact_and_utf8():
    line = emit_cards.dumps({"id": "ru:x", "title": "Заголовок", "norm_dates": [{"norm": "a", "from": None}]})
    assert line == '{"id":"ru:x","title":"Заголовок","norm_dates":[{"norm":"a","from":null}]}'


def test_write_requirements_sorted_one_object_per_line(tmp_path):
    records = [{"id": "ru:b", "x": 1}, {"id": "ru:a", "x": 2}]
    path = emit_cards.write_requirements(records, tmp_path)
    assert path == tmp_path / "requirements.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["id"] for l in lines] == ["ru:a", "ru:b"]
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_write_card_drops_sections_and_keys(tmp_path):
    card = fixture_card()
    path = emit_cards.write_card(card, fixture_ctx(), tmp_path)
    assert path == tmp_path / "cards" / "demo-consent.md"
    text = path.read_text(encoding="utf-8")
    front, body = text[4:].split("\n---\n", 1)
    keys = [line.split(":", 1)[0] for line in front.splitlines() if re.match(r"^[a-z_]+:", line)]
    assert keys[0] == "id" and front.splitlines()[0] == "id: ru:demo-consent"
    for dropped in ("sources", "created", "aliases", "tags", "confidence"):
        assert dropped not in keys
    for kept in ("title", "category", "updated", "verified", "legal_confidence", "volatility", "obligation",
                 "source_kind", "subjects", "models", "products", "acts", "effective_from", "checked",
                 "access", "summary"):
        assert kept in keys
    assert "## See Also" not in body and "## Sources" not in body
    assert "## Правовое основание" in body and "Официальные URL:" in body
    assert "http://example.gov/doc/1" in body
    # Heading inside the code fence is preserved as text, links are sanitized.
    assert "## Не заголовок внутри ограждения" in body
    assert "[политика](demo-policy.md)" in body
    assert "ссылкой [источник](https://example.gov/doc/1) и заметкой.\n" in body
    for leak in ("[[", "raw/", "../topics", "/Us" + "ers/"):
        assert leak not in text, leak


def test_write_card_rewords_frontmatter_and_body(tmp_path):
    card = fixture_card()
    card.fm_raw["summary"] = (
        'summary: "Единственное место wiki (P27); см. [[demo-policy|политику]] ([Политика](demo-policy.md))."'
    )
    card.sections["Исключения"] = "Нет (discovery P11). См. хаб G: в пути P16 не искали."
    text = emit_cards.write_card(card, fixture_ctx(), tmp_path).read_text(encoding="utf-8")
    assert 'summary: "Единственное место базы; см. [политику](demo-policy.md)."' in text
    assert "Нет (предварительный поиск). См. направление G: в базе не искали." in text
    for marker in ("wiki", "P27", "P11", "P16", "discovery", "хаб"):
        assert marker not in text, marker


def test_write_base_plain_facts(tmp_path):
    meta = {
        "base_date": "2026-04-10", "source_sha256": "ab" * 32, "requirements": 2, "cards": 2, "templates": 1,
        "generator_version": "0.1.0",
    }
    path = emit_cards.write_base(meta, tmp_path)
    assert path == tmp_path / "BASE.md"
    text = path.read_text(encoding="utf-8")
    for fact in ("- Base date: 2026-04-10", f"- Source content sha256: {'ab' * 32}", "- Generator version: 0.1.0",
                 "- Requirements: 2", "- Cards: 2", "- Templates: 1"):
        assert fact in text
    assert "commit" not in text.lower() and "git" not in text.lower()
    assert "устар" not in text.lower() and "stale" not in text.lower()


def test_templates_by_card_and_base_date():
    mapping, template_dates = emit_cards.load_templates(TOPIC)
    assert mapping == {"demo-consent": ["demo-form"]}
    assert template_dates == {"demo-form": "2026-04-10"}


def test_legacy_loader_does_not_run_main_or_write_bytecode():
    refs = load_build_refs(REFS)
    assert set(refs.DIRS) == {"A", "B"} and set(refs.TRIGGER) == {"demo-consent", "demo-policy"}
    assert not (REFS.parent / "__pycache__").exists()


@pytest.mark.parametrize(
    "tail",
    [
        "\nmain()\n",
        "\nimport sys\nsys.exit(main())\n",
        "\nraise SystemExit(main())\n",
        "\nif __name__ == '__main__':\n    main()\n",
        "\nresult = main()\n",
        "\nresult: int = main()\n",
        "\ntotal = 0\ntotal += main()\n",
        "\nimport sys\nif len(sys.argv) > 1:\n    main()\n",
        "\ntry:\n    main()\nexcept Exception:\n    pass\n",
    ],
)
def test_legacy_loader_skips_main_even_without_a_guard(tmp_path, tail):
    code = tmp_path / "build_refs.py"
    code.write_text(
        'DIRS = {"A": ("t", "h", ["x"])}\nTRIGGER = {"x": "t"}\n\n\n'
        'def main():\n    raise RuntimeError("main() must not run on load")\n' + tail,
        encoding="utf-8",
    )
    refs = load_build_refs(code)
    assert refs.TRIGGER == {"x": "t"}
    assert not (code.parent / "__pycache__").exists()


def test_source_digest_covers_cards_templates_and_raw_headers(tmp_path):
    topic = tmp_path / "topic"
    shutil.copytree(TOPIC, topic)
    base = build_knowledge.source_digest(topic, REFS)
    assert re.fullmatch(r"[0-9a-f]{64}", base)
    assert build_knowledge.source_digest(topic, REFS) == base

    # A raw body is not read by the build, a raw header and a card are.
    raw = topic / "raw" / "articles" / "demo-official.md"
    raw.write_text(raw.read_text(encoding="utf-8") + "\nещё текст\n", encoding="utf-8")
    assert build_knowledge.source_digest(topic, REFS) == base
    raw.write_text(raw.read_text(encoding="utf-8").replace("example.gov/doc/1", "example.gov/doc/9"), encoding="utf-8")
    changed_raw = build_knowledge.source_digest(topic, REFS)
    assert changed_raw != base
    card = topic / "wiki" / "concepts" / "demo-policy.md"
    card.write_text(card.read_text(encoding="utf-8").replace("Публикуйте", "Публикуйте всегда"), encoding="utf-8")
    changed_card = build_knowledge.source_digest(topic, REFS)
    assert changed_card != changed_raw

    # A template is shipped in full, so a change in its body (not only in its frontmatter) counts.
    template = topic / "wiki" / "references" / "shablon-demo-form.md"
    template.write_text(template.read_text(encoding="utf-8") + "\nещё абзац шаблона\n", encoding="utf-8")
    assert build_knowledge.source_digest(topic, REFS) != changed_card

    # The table module (directory map and triggers) counts too, wherever it lives.
    refs = tmp_path / "elsewhere" / "build_refs.py"
    refs.parent.mkdir()
    refs.write_text(REFS.read_text(encoding="utf-8"), encoding="utf-8")
    with_table = build_knowledge.source_digest(topic, refs)
    assert with_table == build_knowledge.source_digest(topic, REFS)
    refs.write_text(refs.read_text(encoding="utf-8").replace("любая обработка", "иная обработка"), encoding="utf-8")
    assert build_knowledge.source_digest(topic, refs) != with_table


def test_build_pack_and_check_roundtrip(tmp_path):
    out = tmp_path / "ru"
    meta = build_knowledge.build_pack(TOPIC, out, REFS)
    assert meta["requirements"] == 2 and meta["cards"] == 2 and meta["templates"] == 1
    assert meta["base_date"] == "2026-04-10"
    assert meta["source_sha256"] == build_knowledge.source_digest(TOPIC, REFS)
    assert (out / "requirements.jsonl").is_file() and (out / "BASE.md").is_file()
    assert f"- Source content sha256: {meta['source_sha256']}" in (out / "BASE.md").read_text(encoding="utf-8")
    assert sorted(p.name for p in (out / "cards").iterdir()) == ["demo-consent.md", "demo-policy.md"]
    assert emit_cards.is_generated_card(out / "cards" / "demo-policy.md")
    assert build_knowledge.check_pack(TOPIC, out, REFS) == []

    # Hand-written siblings (templates, elements, ...) are not generator output and are ignored.
    (out / "JURISDICTION.md").write_text("manual", encoding="utf-8")
    (out / "templates").mkdir()
    assert build_knowledge.check_pack(TOPIC, out, REFS) == []

    (out / "cards" / "notes.md").write_text("hand-written", encoding="utf-8")
    assert build_knowledge.check_pack(TOPIC, out, REFS) == []

    original = (out / "cards" / "demo-policy.md").read_text(encoding="utf-8")
    (out / "cards" / "demo-policy.md").write_text(original + "extra\n", encoding="utf-8")
    (out / "cards" / "gone.md").write_text("---\nid: ru:gone\n---\n", encoding="utf-8")
    diffs = build_knowledge.check_pack(TOPIC, out, REFS)
    assert diffs == ["differs: cards/demo-policy.md", "unexpected: cards/gone.md"]

    # Rebuilding repairs generated files, removes stale generated cards and keeps hand-written ones.
    build_knowledge.build_pack(TOPIC, out, REFS)
    assert not (out / "cards" / "gone.md").exists()
    assert (out / "cards" / "notes.md").read_text(encoding="utf-8") == "hand-written"
    assert (out / "JURISDICTION.md").read_text(encoding="utf-8") == "manual"
    assert build_knowledge.check_pack(TOPIC, out, REFS) == []


def test_cli_check_exit_codes(tmp_path):
    out = tmp_path / "ru"
    args = ["--wiki", str(TOPIC), "--build-refs", str(REFS), "--out", str(out)]
    assert build_knowledge.main(args) == 0
    assert build_knowledge.main(args + ["--check"]) == 0
    (out / "requirements.jsonl").write_text("[]\n", encoding="utf-8")
    assert build_knowledge.main(args + ["--check"]) == 1
    missing = ["--wiki", str(tmp_path / "missing"), "--build-refs", str(REFS), "--out", str(out)]
    assert build_knowledge.main(missing) == 2


def test_cli_requires_build_refs_together_with_wiki(tmp_path, capsys):
    out = tmp_path / "ru"
    assert build_knowledge.main(["--wiki", str(TOPIC), "--out", str(out)]) == 2
    error = capsys.readouterr().err
    assert "--build-refs is required together with --wiki" in error and "build_refs.py" in error
    assert not out.exists()


def test_cli_reports_a_missing_table_module(tmp_path, capsys):
    args = ["--wiki", str(TOPIC), "--build-refs", str(tmp_path / "nope.py"), "--out", str(tmp_path / "ru")]
    assert build_knowledge.main(args) == 2
    assert "build_refs.py not found" in capsys.readouterr().err


# ---------------------------------------------------------- integration tests

needs_wiki = pytest.mark.skipif(not (WIKI and BUILD_REFS), reason=SKIP_REASON)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    out = tmp_path_factory.mktemp("pack") / "ru"
    code = build_knowledge.main(["--wiki", WIKI, "--build-refs", BUILD_REFS, "--out", str(out)])
    assert code == 0
    lines = (out / "requirements.jsonl").read_text(encoding="utf-8").splitlines()
    return out, lines, [json.loads(line) for line in lines]


@pytest.fixture(scope="module")
def source_cards():
    folder = Path(WIKI) / "wiki" / "concepts"
    return {p.stem: load_card(p) for p in sorted(folder.glob("*.md")) if p.name != "_index.md"}


@needs_wiki
def test_219_requirements_and_cards(pack):
    out, _, records = pack
    assert len(records) == 219
    assert [r["id"] for r in records] == sorted(r["id"] for r in records)
    assert len({r["id"] for r in records}) == 219
    cards = sorted(p.name for p in (out / "cards").iterdir())
    assert len(cards) == 219
    assert cards == sorted(f"{r['id'][3:]}.md" for r in records)
    assert all(r["card"] == f"cards/{r['id'][3:]}.md" for r in records)


def written_basis(out, record):
    """Legal-basis section of the written card of a record."""
    _, body = parse_frontmatter((out / record["card"]).read_text(encoding="utf-8"))
    return split_sections(body)[BASIS]


def independent_urls(section):
    """Every http(s) URL on every line of ``section``, once, in order, minus lines about unofficial
    copies and minus mirrors of official texts (own definition, not the generator's code)."""
    urls = []
    for line in section.splitlines():
        if "еофициальн" in line:
            continue
        for url in re.findall(r"https?://[^\s)<>\]]+", line):
            url = url.rstrip(".,;:")
            host = re.match(r"https?://([^/?#]+)", url).group(1).lower()
            mirror = host.endswith(("sudact.ru", "garant.ru", "consultant.ru")) or host == "xn--90afdbaav0bd1afy6eub5d.xn--p1ai"
            if not mirror and url not in urls:
                urls.append(url)
    return urls


@needs_wiki
def test_official_urls_are_every_non_mirror_url_of_the_written_basis_section(pack):
    out, _, records = pack
    total = 0
    for r in records:
        expected = independent_urls(written_basis(out, r))
        assert expected, r["id"]
        assert r["official_urls"] == expected, r["id"]
        total += len(expected)
    print(f"official URLs kept: {total}")
    assert total == sum(len(r["official_urls"]) for r in records)


@needs_wiki
def test_acts_and_norms_are_complete(pack, source_cards):
    _, _, records = pack
    for r in records:
        card = source_cards[r["id"][3:]]
        assert r["acts"] == [scrub(unlink(act)) for act in card.fm["acts"]], r["id"]
        assert r["norm_dates"] == norm_dates(scrub(card.sections[BASIS])), r["id"]
        source_text = "\n".join(card.fm["acts"]) + card.sections[BASIS]
        for text in r["acts"] + [entry["norm"] for entry in r["norm_dates"]]:
            assert "…" not in text or "…" in source_text, r["id"]


@needs_wiki
def test_enum_fields_valid(pack):
    _, _, records = pack
    for r in records:
        assert list(r) == REQUIRED_KEYS, r["id"]
        assert r["obligation"] in OBLIGATION, r["id"]
        assert r["source_kind"] in SOURCE_KIND, r["id"]
        assert r["legal_confidence"] in CONFIDENCE, r["id"]
        assert r["volatility"] in VOLATILITY, r["id"]
        assert r["subjects"] and set(r["subjects"]) <= SUBJECTS, r["id"]
        assert r["models"] and set(r["models"]) <= MODELS, r["id"]
        assert r["products"] and set(r["products"]) <= PRODUCTS, r["id"]
        assert re.fullmatch(r"[A-N]", r["dir"]), r["id"]
        assert r["effective_from"] == "mixed" or re.fullmatch(r"\d{4}-\d\d-\d\d", r["effective_from"]), r["id"]
        assert r["title"] and r["summary"] and r["trigger"] and r["acts"], r["id"]
        assert r["tech"] and r["cannot_check"], r["id"]
        assert all(t["kind"] in TECH_KINDS and len(t["text"]) <= 200 for t in r["tech"]), r["id"]
        assert all(len(c) <= 200 for c in r["cannot_check"]), r["id"]
        for nd in r["norm_dates"]:
            assert nd["from"] is None or re.fullmatch(r"\d{4}-\d\d-\d\d", nd["from"]), r["id"]


@needs_wiki
def test_tech_kinds_follow_the_source_kind_of_the_card(pack, source_cards):
    _, _, records = pack
    seen = {}
    for r in records:
        card = source_cards[r["id"][3:]]
        full = {t["kind"] for t in classify_tech(card.sections[TECH], 200, source_kind=card.fm["source_kind"])}
        kept = {t["kind"] for t in r["tech"]}
        seen.setdefault(r["source_kind"], set()).update(full)
        assert kept <= full, r["id"]
        if r["source_kind"] == "store-policy":
            assert full == {"platform"}, r["id"]
        if r["source_kind"] not in ("law", "bylaw"):
            assert "norm" not in full, r["id"]
    print({kind: sorted(kinds) for kind, kinds in seen.items()})
    assert "norm" in seen["law"] and seen["store-policy"] == {"platform"}
    assert {t["kind"] for r in records for t in r["tech"]} == TECH_KINDS


@needs_wiki
def test_no_shipped_item_has_unbalanced_parentheses(pack):
    _, _, records = pack
    items = [t["text"] for r in records for t in r["tech"]] + [c for r in records for c in r["cannot_check"]]
    unbalanced = [text for text in items if text.count("(") != text.count(")")]
    assert not unbalanced, unbalanced[:5]


@needs_wiki
def test_authority_positions_are_not_norms(pack, source_cards):
    _, _, records = pack
    for r in records:
        for t in r["tech"]:
            if t["kind"] == "norm":
                assert not re.search(r"позици\w* (?:органа|РКН|ФНС|ФАС|ЦБ|Роспотребнадзора)", t["text"]), (r["id"], t)
                assert "этого не требует" not in t["text"], (r["id"], t)
    card = source_cards["znak-informacionnoy-produkcii-smi"]
    for item in classify_tech(card.sections[TECH], 200, source_kind=card.fm["source_kind"]):
        if "РКН" in item["text"] or "позиция" in item["text"]:
            assert item["kind"] != "norm", item
    items = classify_tech(card.sections[TECH], 200, source_kind=card.fm["source_kind"])
    assert any("по рекомендациям для редакций" in i["text"] and i["kind"] == "interpretation" for i in items)
    for slug, needle in (
        ("cheki-samozanyatogo-npd", "(FAQ ФНС)"),
        ("vozvrat-tovara-pri-distancionnoy-prodazhe", "(Пленум № 17 п. 43)"),
        ("zapret-navyazyvaniya-uslug", "(ВС, п. 12)"),
        ("publichnaya-oferta-i-podtverzhdenie-zakaza", "(Обзор п. 4"),
    ):
        card = source_cards[slug]
        found = [i for i in classify_tech(card.sections[TECH], 5000, source_kind=card.fm["source_kind"]) if needle in i["text"]]
        assert found and all(i["kind"] == "interpretation" for i in found), slug
    onlayn = classify_tech(source_cards["onlayn-kkt-i-elektronnyy-chek"].sections[TECH], 5000, source_kind="law")
    assert any("(позиция ФНС)" in i["text"] and i["kind"] == "interpretation" for i in onlayn)


@needs_wiki
def test_eight_requirements_with_future_effective_from(pack):
    _, _, records = pack
    future = [r["id"] for r in records if r["effective_from"] != "mixed" and r["effective_from"] > LAUNCH_DATE]
    assert len(future) == 8, future


@needs_wiki
def test_average_record_size(pack):
    _, lines, _ = pack
    sizes = [len(line) for line in lines]
    average = sum(sizes) / len(sizes)
    print(f"requirements.jsonl: average {average:.0f} chars, max {max(sizes)} chars")
    assert average <= 3000


@needs_wiki
def test_templates_field_matches_template_sources(pack):
    _, _, records = pack
    used = {t for r in records for t in r["templates"]}
    assert len(used) == 9
    assert all(re.fullmatch(r"[a-z0-9-]+", t) for t in used)


PRIVATE_MARKERS = [
    r"\[\[", r"raw/", r"wiki/", r"\.\./topics", r"\.\./references", r"/Us" + r"ers/", r"(?i)llm" + r"-wiki",
    r"\bP\d{1,2}\b", r"(?i)discovery", r"(?i)\bхаб(?:а|е|у|ом)?\b", r"(?i)(?<![a-z])wiki(?![a-z])",
    r"(?i)schema\.md", r"(?i)ingest", r"(?i)path report", r"(?i)modern-web-app-development",
    r"(?i)\bпут[иь]\s+P\d",
]


@needs_wiki
def test_generated_pack_has_no_private_markers(pack):
    out, _, _ = pack
    hits = []
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in PRIVATE_MARKERS:
            match = re.search(marker, text)
            if match:
                context = text[max(0, match.start() - 30):match.end() + 30]
                hits.append(f"{path.relative_to(out)}: {marker!r}: {context!r}")
    assert not hits, "\n".join(hits[:20])


@needs_wiki
def test_card_links_resolve_inside_pack(pack):
    out, _, _ = pack
    names = {p.name for p in (out / "cards").iterdir()}
    templates = {p.stem[len("shablon-"):] for p in (Path(WIKI) / "wiki" / "references").glob("shablon-*.md")}
    broken = []
    for path in sorted((out / "cards").iterdir()):
        for target in re.findall(r"\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://")):
                continue
            target = target.split("#", 1)[0]
            template = re.fullmatch(r"\.\./templates/([a-z0-9-]+)/text\.md", target)
            if template:
                # The template pages are written by a later step; the folder must name a known template.
                if template.group(1) not in templates:
                    broken.append(f"{path.name}: {target}")
            elif target not in names:
                broken.append(f"{path.name}: {target}")
    assert not broken, "\n".join(broken[:20])


@needs_wiki
def test_base_md_has_content_hash_and_no_git_hash(pack):
    out, _, _ = pack
    text = (out / "BASE.md").read_text(encoding="utf-8")
    assert re.search(r"^- Source content sha256: [0-9a-f]{64}$", text, re.M)
    assert "commit" not in text.lower()


@needs_wiki
def test_check_exits_zero_on_rebuild(pack):
    out, _, _ = pack
    assert build_knowledge.main(["--wiki", WIKI, "--build-refs", BUILD_REFS, "--out", str(out), "--check"]) == 0
