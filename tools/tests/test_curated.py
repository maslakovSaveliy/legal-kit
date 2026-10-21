"""Checks for the hand-written (curated) files of the jurisdiction packs.

Covers jurisdictions/README.md and, in jurisdictions/ru/: JURISDICTION.md,
owner-questions.md, registries.md and documents/*.md. Stdlib + pytest only;
paths are resolved from this file, so the test runs from any directory.
"""

import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUR_DIR = ROOT / "skills" / "legal-kit" / "references" / "jurisdictions"
CONTRACT_MD = JUR_DIR / "README.md"
RU_DIR = JUR_DIR / "ru"
JURISDICTION_MD = RU_DIR / "JURISDICTION.md"
OWNER_QUESTIONS_MD = RU_DIR / "owner-questions.md"
REGISTRIES_MD = RU_DIR / "registries.md"
DOCUMENTS_DIR = RU_DIR / "documents"

EXPECTED_DOCUMENTS = (
    "rkn-notification",
    "cross-border-notification",
    "poruchenie",
    "prikaz-otvetstvennyy",
    "lokalnye-akty",
    "incident-reglament",
    "subject-requests",
    "user-agreement",
    "image-consent",
    "promo-rules",
    "gift-cards",
    "ord-erir-checklist",
    "kkt-checklist",
)

# Pack files written by other tasks (knowledge generator, template generator,
# feature map). Until they land, their absence is not a failure here. The
# controller empties this set once those tasks are merged.
PENDING_FILES = frozenset(
    {
        "BASE.md",
        "requirements.jsonl",
        "cards/",
        "templates/",
        "elements.json",
        "placeholders.json",
        "forbidden-clauses.json",
        "feature-map.json",
    }
)

# Documents for which the knowledge base has no norm: the spec must send the
# skill to research at runtime.
RESEARCH_REQUIRED_DOCUMENTS = ("gift-cards", "promo-rules")
RESEARCH_MARKER = "доисследовать по research-rules"

DOCUMENT_SECTIONS = (
    "Назначение",
    "Основания",
    "Обязательные элементы",
    "Что найти при запуске",
    "Черновик",
    "Кто подписывает и подаёт",
)
ELEMENTS_HEADER = ("Элемент", "Норма", "id", "Метка")
LABELS = frozenset(
    {"норма", "практика", "трактовка", "вывод", "позиция органа", "правило стора"}
)
REGISTRY_FIELDS = ("Требования:", "Когда проверять:", "При отказе:")
# A «норма» row must cite a law or regulation, not guidance, court reviews or store rules.
NON_NORM_SOURCE_RE = re.compile(
    r"FAQ|инструкц|Пленум|Обзор|руководств|письм|рекомендац|правил\w* стор|позици",
    re.IGNORECASE,
)
# A registry that can hit a captcha, a Gosuslugi login or a geo-block must hand off to the user.
MANUAL_TRIGGER_RE = re.compile(r"капч|Госуслуг|гео-|российск\w* IP", re.IGNORECASE)
MANUAL_STATUS = "`manual`"

ANSWERS_SCHEMA_SECTION = "Схема answers.json"
REQUIRED_ANSWER_KEYS = frozenset(
    {
        "version",
        "updated",
        "product.name",
        "product.summary",
        "product.kinds",
        "product.urls",
        "product.stores.app_store",
        "product.stores.google_play",
        "product.stores.rustore",
        "product.stores.appgallery",
        "product.repo",
        "owner.status",
        "owner.name",
        "owner.inn",
        "owner.ogrn",
        "owner.country",
        "owner.address",
        "owner.email",
        "owner.phone",
        "owner.withheld",
        "audience.b2c",
        "audience.b2b",
        "audience.minors",
        "audience.countries",
        "business.sectors",
        "business.revenue_over_20m",
        "business.rkn_notified",
        "decisions.block_counters",
        "decisions.apply_changes",
        "decisions.commit_legal_dir",
        "decisions.consent_at_forms",
        "document_facts",
    }
)
ANSWER_KEY_RE = re.compile(r"`((?:product|owner|audience|business|decisions)\.[a-z_.]+)`")

MAX_START_QUESTIONS = 5
MAX_CONFIRMATION_QUESTIONS = 10
DOCUMENT_REQUEST_ITEMS = 18
TOC_MIN_LINES = 100
TOC_HEADINGS = ("Оглавление", "Contents")
TOC_SEARCH_LINES = 15

# Hosts of official sources (laws, regulators, courts, official publication).
OFFICIAL_HOST_SUFFIXES = (
    "gov.ru",
    "nalog.ru",
    "vsrf.ru",
    "cbr.ru",
    "rg.ru",
    "rospotrebnadzor.ru",
)

ID_RE = re.compile(r"(?<![\w.:/-])ru:([a-z0-9]+(?:-[a-z0-9]+)*)")
URL_RE = re.compile(r"https?://[^\s)>\]`|]+")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
NUMBERED_RE = re.compile(r"^\d+\.\s+\S")
BACKTICK_RE = re.compile(r"`([^`]+)`")
ANCHOR_RE = re.compile(r"\]\(#([^)]+)\)")


# ---------------------------------------------------------------- helpers


def read(path):
    return path.read_text(encoding="utf-8")


def document_paths():
    return [DOCUMENTS_DIR / f"{name}.md" for name in EXPECTED_DOCUMENTS]


def curated_paths():
    return [CONTRACT_MD, JURISDICTION_MD, OWNER_QUESTIONS_MD, REGISTRIES_MD, *document_paths()]


def rel(path):
    return path.relative_to(ROOT).as_posix()


def unfenced_lines(text):
    """Yield (index, line) for lines outside fenced code blocks."""
    fenced = False
    for i, line in enumerate(text.splitlines()):
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield i, line


def headings(text):
    """Return [(level, title)] for headings outside fenced code blocks."""
    found = []
    for _, line in unfenced_lines(text):
        match = HEADING_RE.match(line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def section(text, title, level=2):
    """Lines of the section with the given heading, up to the next heading of the same or higher level."""
    lines = text.splitlines()
    start = None
    fenced = False
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        depth = len(match.group(1))
        if start is None:
            if depth == level and match.group(2) == title:
                start = i + 1
        elif depth <= level:
            return lines[start:i]
    if start is None:
        raise AssertionError(f"section '{title}' not found")
    return lines[start:]


def github_anchor(title):
    """GitHub-style heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    kept = []
    for ch in title.lower():
        if ch.isalnum() or ch in "-_ " or unicodedata.category(ch).startswith("M"):
            kept.append(ch)
    return "".join(kept).replace(" ", "-")


def heading_anchors(text):
    anchors = set()
    seen = {}
    for _, title in headings(text):
        plain = re.sub(r"`([^`]*)`", r"\1", title)
        base = github_anchor(plain)
        count = seen.get(base, 0)
        anchors.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return anchors


def table_rows(lines):
    """Rows of the first Markdown table in lines, as lists of stripped cells (header first, no separator)."""
    rows = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            rows.append(cells)
        elif rows:
            break
    return rows


def first_column_paths(lines):
    return {
        path
        for row in table_rows(lines)[1:]
        for path in BACKTICK_RE.findall(row[0])
    }


def known_ids():
    jsonl = RU_DIR / "requirements.jsonl"
    if jsonl.is_file():
        return {
            json.loads(line)["id"]
            for line in read(jsonl).splitlines()
            if line.strip()
        }
    cards = RU_DIR / "cards"
    found = {f"ru:{card.stem}" for card in cards.glob("*.md")} if cards.is_dir() else set()
    if found:
        return found
    pytest.fail(
        "No requirement index: neither jurisdictions/ru/requirements.jsonl nor "
        "jurisdictions/ru/cards/*.md exists. Both are generated by "
        "tools/build_knowledge.py; build the pack, then re-run this test."
    )


def is_official(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in OFFICIAL_HOST_SUFFIXES)


def pack_path_exists(path):
    target = RU_DIR / path.rstrip("/")
    if path.endswith("/"):
        return target.is_dir() and any(target.iterdir())
    return target.is_file()


# ------------------------------------------------------------------ tests


def test_curated_files_exist():
    missing = [rel(p) for p in curated_paths() if not p.is_file()]
    assert not missing, "missing curated files:\n" + "\n".join(missing)


def test_documents_dir_has_exactly_expected_files():
    present = {p.stem for p in DOCUMENTS_DIR.glob("*.md")}
    assert present == set(EXPECTED_DOCUMENTS)


def test_all_requirement_ids_exist():
    ids = known_ids()
    unknown = []
    for path in curated_paths():
        for match in ID_RE.finditer(read(path)):
            requirement = f"ru:{match.group(1)}"
            if requirement not in ids:
                unknown.append(f"{rel(path)}: {requirement}")
    assert not unknown, "unknown requirement ids:\n" + "\n".join(sorted(set(unknown)))


@pytest.mark.parametrize("path", document_paths(), ids=EXPECTED_DOCUMENTS)
def test_document_has_official_url(path):
    urls = URL_RE.findall(read(path))
    assert any(is_official(url) for url in urls), f"{rel(path)}: no official http(s) URL"


@pytest.mark.parametrize("path", document_paths(), ids=EXPECTED_DOCUMENTS)
def test_document_has_required_sections(path):
    titles = [title for level, title in headings(read(path)) if level == 2]
    missing = [name for name in DOCUMENT_SECTIONS if name not in titles]
    assert not missing, f"{rel(path)}: missing sections {missing}"


@pytest.mark.parametrize("path", document_paths(), ids=EXPECTED_DOCUMENTS)
def test_document_names_its_draft_path(path):
    assert f".legal/drafts/{path.stem}.md" in read(path)


@pytest.mark.parametrize("path", document_paths(), ids=EXPECTED_DOCUMENTS)
def test_document_elements_table_is_labelled(path):
    rows = table_rows(section(read(path), "Обязательные элементы"))
    assert rows, f"{rel(path)}: no elements table"
    assert tuple(rows[0]) == ELEMENTS_HEADER, f"{rel(path)}: header {rows[0]}"
    assert len(rows) > 1, f"{rel(path)}: elements table is empty"
    problems = []
    for row in rows[1:]:
        if len(row) != len(ELEMENTS_HEADER):
            problems.append(f"wrong cell count: {row}")
            continue
        element, norm, ids, label = row
        if not ID_RE.search(ids):
            problems.append(f"no requirement id: {element}")
        if label.lower() not in LABELS:
            problems.append(f"unknown label {label!r}: {element}")
        if label.lower() == "норма" and norm in ("", "—", "-"):
            problems.append(f"label 'норма' without a norm: {element}")
        if label.lower() == "норма" and NON_NORM_SOURCE_RE.search(norm):
            problems.append(f"label 'норма' cites a non-norm source {norm!r}: {element}")
    assert not problems, f"{rel(path)}:\n" + "\n".join(problems)


@pytest.mark.parametrize("name", RESEARCH_REQUIRED_DOCUMENTS)
def test_documents_without_norm_send_to_research(name):
    assert RESEARCH_MARKER in read(DOCUMENTS_DIR / f"{name}.md")


@pytest.mark.parametrize("path", curated_paths(), ids=lambda p: rel(p))
def test_long_files_start_with_toc(path):
    text = read(path)
    lines = text.splitlines()
    if len(lines) <= TOC_MIN_LINES:
        return
    top = [title for _, title in headings("\n".join(lines[:TOC_SEARCH_LINES]))]
    assert any(t in TOC_HEADINGS for t in top), (
        f"{rel(path)} has {len(lines)} lines but no TOC heading in the first {TOC_SEARCH_LINES} lines"
    )
    toc_title = next(t for t in top if t in TOC_HEADINGS)
    links = ANCHOR_RE.findall("\n".join(section(text, toc_title)))
    assert len(links) >= 2, f"{rel(path)}: TOC has fewer than two links"
    anchors = heading_anchors(text)
    broken = [link for link in links if link not in anchors]
    assert not broken, f"{rel(path)}: TOC links without a heading: {broken}"


def test_jurisdiction_lists_contract_files():
    required = first_column_paths(section(read(CONTRACT_MD), "Required files"))
    listed = first_column_paths(section(read(JURISDICTION_MD), "Required files"))
    assert required, "contract lists no required files"
    missing = sorted(required - listed)
    assert not missing, f"JURISDICTION.md does not list contract files: {missing}"


def test_jurisdiction_required_files_exist():
    listed = first_column_paths(section(read(JURISDICTION_MD), "Required files"))
    assert listed, "JURISDICTION.md lists no required files"
    missing = sorted(p for p in listed if p not in PENDING_FILES and not pack_path_exists(p))
    assert not missing, f"required pack files missing: {missing}"


def test_jurisdiction_lists_every_document():
    text = read(JURISDICTION_MD)
    missing = [n for n in EXPECTED_DOCUMENTS if f"documents/{n}.md" not in text]
    assert not missing, f"JURISDICTION.md does not list documents: {missing}"


def test_jurisdiction_declares_id_prefix():
    assert "`ru:`" in read(JURISDICTION_MD)


def numbered_items(lines):
    return [line for line in lines if NUMBERED_RE.match(line)]


def test_start_questions_limit():
    items = numbered_items(section(read(OWNER_QUESTIONS_MD), "Стартовые вопросы"))
    assert 1 <= len(items) <= MAX_START_QUESTIONS, f"{len(items)} start questions"


def test_confirmation_block_limit():
    items = numbered_items(section(read(OWNER_QUESTIONS_MD), "Блок подтверждения"))
    assert 1 <= len(items) <= MAX_CONFIRMATION_QUESTIONS, f"{len(items)} confirmation questions"


def test_document_request_has_18_items():
    items = numbered_items(section(read(OWNER_QUESTIONS_MD), "Сводный запрос документов"))
    assert len(items) == DOCUMENT_REQUEST_ITEMS, f"{len(items)} items"


def test_owner_questions_cover_requirements():
    lines = section(read(OWNER_QUESTIONS_MD), "Вопросы по требованиям")
    ids = {f"ru:{match.group(1)}" for line in lines for match in ID_RE.finditer(line)}
    known = known_ids()
    assert ids == known, (
        f"missing: {sorted(known - ids)}; unknown: {sorted(ids - known)}"
    )


def fenced_block(lines, language):
    """Content of the first fenced block with the given info string."""
    inside, body = False, []
    for line in lines:
        stripped = line.strip()
        if not inside and stripped == f"```{language}":
            inside = True
        elif inside and stripped == "```":
            return "\n".join(body)
        elif inside:
            body.append(line)
    raise AssertionError(f"no fenced ```{language} block")


def dotted_keys(data, prefix=""):
    keys = set()
    for key, value in data.items():
        path = f"{prefix}{key}"
        keys.add(path)
        if isinstance(value, dict):
            keys |= dotted_keys(value, f"{path}.")
    return keys


def answers_schema_keys():
    lines = section(read(OWNER_QUESTIONS_MD), ANSWERS_SCHEMA_SECTION)
    return dotted_keys(json.loads(fenced_block(lines, "json")))


def test_answers_schema_lists_every_key():
    missing = sorted(REQUIRED_ANSWER_KEYS - answers_schema_keys())
    assert not missing, f"answers.json schema lacks keys: {missing}"


def test_answer_keys_used_in_questions_are_in_schema():
    schema = answers_schema_keys()
    used = set(ANSWER_KEY_RE.findall(read(OWNER_QUESTIONS_MD)))
    unknown = sorted(key for key in used if key not in schema)
    assert not unknown, f"keys used in questions but absent from the schema: {unknown}"


def registry_sections():
    text = read(REGISTRIES_MD)
    lines = section(text, "Реестры")
    blocks, current = {}, None
    for line in lines:
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 3:
            current = match.group(2)
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line)
    return blocks


def test_registries_have_ids_timing_and_fallback():
    blocks = registry_sections()
    assert len(blocks) >= 9, f"only {len(blocks)} registries"
    problems = []
    for name, lines in blocks.items():
        body = "\n".join(lines)
        problems.extend(f"{name}: no '{field}'" for field in REGISTRY_FIELDS if field not in body)
        if not ID_RE.search(body):
            problems.append(f"{name}: no requirement id")
        if MANUAL_TRIGGER_RE.search(body) and MANUAL_STATUS not in body:
            problems.append(f"{name}: captcha, login or geo-block without a `manual` hand-off")
    assert not problems, "\n".join(problems)
