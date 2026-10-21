"""Checks for the stack reference files (skills/legal-kit/references/stacks).

Stdlib only. The repo root is located from this file, so the test runs from
any working directory.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STACKS_DIR = ROOT / "skills" / "legal-kit" / "references" / "stacks"

STACKS = (
    "nextjs",
    "react",
    "nestjs",
    "react-native",
    "flutter",
    "swift",
    "python",
    "static-html",
    "generic-web",
    "no-code",
)

# Stacks whose Legal pages section creates web pages. Mobile stacks only link
# to documents hosted on the website, so the route rule does not apply to them.
PAGE_STACKS = ("nextjs", "react", "nestjs", "python", "static-html", "generic-web", "no-code")

# Every stack file carries these sections. Each entry is a regex searched in
# the level-2 headings of the file (case-insensitive), so a longer heading such
# as "## Footer and links" or a merged one such as "## Footer and i18n" still
# satisfies the concept it names.
REQUIRED_SECTIONS = {
    "Detect": r"detect",
    "Legal pages": r"legal pages",
    "Consent checkbox": r"consent checkbox",
    "Analytics gated by consent": r"analytics gated by consent",
    "Consent banner": r"consent banner",
    "Consent log": r"consent log",
    "Footer": r"footer",
    "i18n": r"i18n",
    "Verify": r"verify",
}

# The one request body every client and server snippet must use.
PAYLOAD_KEYS = {"subjectId", "consentVersion", "formId", "channel", "action"}
PAYLOAD_LINE = "`{ subjectId, consentVersion, formId, channel, action }`"
LOG_ONLY_RULE = "Log only `grant` and `revoke`"

MAX_LINES = 190
TOC_THRESHOLD = 100

# Legal citations, dates and amounts belong to the knowledge pack, never to the
# stack files. Cyrillic and Latin spellings are both covered.
CITATION_RE = re.compile(
    r"ст\.|ФЗ|\b\d{2,3}-ФЗ|\bст\s*\d"
    r"|\b\d{2,3}-FZ\b|\bFZ\b|Federal Law|\bArt\.\s*\d|\bArticles?\s+\d|\bpenalt|\bfines?\b",
    re.IGNORECASE,
)
DATE_AMOUNT_RE = re.compile(
    r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"            # ISO date
    r"|\b\d{1,2}\.\d{1,2}\.(?:19|20)\d{2}\b"     # dotted date
    r"|\b20[0-4]\d\b"                            # bare year
    r"|\d\s*(?:руб|₽|RUB\b|rubles|roubles)",     # amount in roubles
    re.IGNORECASE,
)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
SNAKE_JSON_KEY_RE = re.compile(
    r"(?<![\w'\"])['\"]?(?:subject_id|consent_version|form_id|text_sha256|user_agent)['\"]?\s*:"
)


def read(stack):
    return (STACKS_DIR / f"{stack}.md").read_text(encoding="utf-8")


def headings(text):
    """Level-2 headings outside fenced code blocks."""
    result = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.startswith("## "):
            result.append(line[3:].strip())
    return result


def section(text, name_regex):
    """Body of the first level-2 section whose heading matches name_regex."""
    body, inside, fenced = [], False, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if inside:
                break
            inside = re.search(name_regex, line[3:], re.IGNORECASE) is not None
            continue
        if inside:
            body.append(line)
    assert body, f"no section matching {name_regex!r}"
    return "\n".join(body)


def brace_groups(text):
    """Single-line, non-nested {...} groups."""
    return re.findall(r"\{[^{}\n]*\}", text)


def group_keys(group):
    keys = set()
    for part in group.strip("{} ").split(","):
        key = part.split(":")[0].strip().strip("'\"")
        if key:
            keys.add(key)
    return keys


def payload_groups(text):
    """Brace groups that look like a consent-log request body."""
    return [g for g in brace_groups(text) if "subjectId" in g and "consentVersion" in g]


def test_ten_stack_files_exist():
    for stack in STACKS:
        assert (STACKS_DIR / f"{stack}.md").is_file(), f"missing {stack}.md"


def test_no_unexpected_stack_files():
    present = {p.stem for p in STACKS_DIR.glob("*.md")}
    assert present == set(STACKS)


@pytest.mark.parametrize("stack", STACKS)
def test_required_sections(stack):
    heads = [h.lower() for h in headings(read(stack))]
    for name, pattern in REQUIRED_SECTIONS.items():
        found = any(re.search(pattern, h) for h in heads)
        assert found, f"{stack}.md: no '## ...{name}...' heading (have: {heads})"


@pytest.mark.parametrize("stack", STACKS)
def test_toc_for_long_files(stack):
    text = read(stack)
    lines = text.splitlines()
    assert len(lines) <= MAX_LINES, f"{stack}.md has {len(lines)} lines"
    if len(lines) <= TOC_THRESHOLD:
        return
    # The TOC must sit before the first level-2 section and link to anchors.
    first_h2 = next(i for i, ln in enumerate(lines) if ln.startswith("## "))
    head = "\n".join(lines[:first_h2]).lower()
    assert "contents" in head, f"{stack}.md: no 'Contents' marker before first section"
    anchors = re.findall(r"\]\(#[a-z0-9-]+\)", head)
    assert len(anchors) >= len(REQUIRED_SECTIONS) - 2, f"{stack}.md: TOC too thin"


@pytest.mark.parametrize("stack", STACKS)
def test_toc_anchors_resolve(stack):
    text = read(stack)
    slugs = set()
    for h in headings(text):
        slug = re.sub(r"[^a-z0-9 -]", "", h.lower()).strip().replace(" ", "-")
        slugs.add(slug)
    for anchor in re.findall(r"\]\(#([a-z0-9-]+)\)", text):
        assert anchor in slugs, f"{stack}.md: TOC anchor #{anchor} has no heading"


@pytest.mark.parametrize("stack", STACKS)
def test_no_legal_citations(stack):
    text = read(stack)
    hit = CITATION_RE.search(text)
    assert hit is None, f"{stack}.md contains a legal citation: {hit.group(0)!r}"


@pytest.mark.parametrize("stack", STACKS)
def test_no_dates_or_amounts(stack):
    text = read(stack)
    hit = DATE_AMOUNT_RE.search(text)
    assert hit is None, f"{stack}.md contains a date or amount: {hit.group(0)!r}"


def test_citation_and_date_patterns_catch_samples():
    for sample in ("ст. 9", "152-ФЗ", "see 152-FZ", "Federal Law", "Art. 9", "Article 18", "fine of", "penalties"):
        assert CITATION_RE.search(sample), sample
    for sample in ("since 2025-09-01", "from 01.09.2025", "in 2026", "5 000 руб", "10000 RUB"):
        assert DATE_AMOUNT_RE.search(sample), sample
    for sample in ("Next 16", "WordPress 6.3+", "refine(Boolean)", "data-ym=\"12345678\""):
        assert not CITATION_RE.search(sample) and not DATE_AMOUNT_RE.search(sample), sample


@pytest.mark.parametrize("stack", STACKS)
def test_english_prose_with_russian_only_in_examples(stack):
    # The files are English. Cyrillic is allowed only in short snippets such
    # as Russian label examples; a Cyrillic-heavy file means prose slipped in.
    text = read(stack)
    cyr = len(CYRILLIC_RE.findall(text))
    assert cyr < 0.04 * len(text), f"{stack}.md is too Cyrillic-heavy ({cyr} chars)"


@pytest.mark.parametrize("stack", STACKS)
def test_no_private_paths(stack):
    text = read(stack)
    for bad in ("/Us" + "ers/", "[[", "raw/", "llm" + "-wiki", "../topics"):
        assert bad not in text, f"{stack}.md leaks {bad!r}"


@pytest.mark.parametrize("stack", STACKS)
def test_checkbox_rule_stated_in_checkbox_section(stack):
    body = section(read(stack), r"consent checkbox").lower()
    assert "unchecked by default" in body, f"{stack}.md: checkbox section lacks 'unchecked by default'"
    assert "offer" in body, f"{stack}.md: checkbox section does not separate the box from the offer/terms"


@pytest.mark.parametrize("stack", STACKS)
def test_consent_log_rules(stack):
    body = section(read(stack), r"consent log")
    assert "NEVER introduce a new database" in body, f"{stack}.md: missing the no-new-database rule"
    assert PAYLOAD_LINE in body, f"{stack}.md: Consent log lacks the canonical payload line"
    assert "holds personal data" in body and "never store form contents" in body, (
        f"{stack}.md: Consent log lacks the line about the log's own personal data"
    )
    assert LOG_ONLY_RULE in body, f"{stack}.md: Consent log lacks the grant/revoke-only rule"


@pytest.mark.parametrize("stack", STACKS)
def test_no_refusal_ids(stack):
    # First-time refusals are not logged, so no id logic exists for them.
    text = read(stack)
    for bad in ("session-scoped", "per-launch", "sessionStorage"):
        assert bad not in text, f"{stack}.md still has refusal-id logic: {bad!r}"


@pytest.mark.parametrize("stack", STACKS)
def test_banner_section_rules(stack):
    body = section(read(stack), r"consent banner").lower()
    assert "marketing" in body, f"{stack}.md: banner section lacks the analytics/marketing split"
    assert "bump" in body or "no longer matches" in body, f"{stack}.md: banner section lacks re-consent on a version change"


@pytest.mark.parametrize("stack", PAGE_STACKS)
def test_existing_route_takes_priority(stack):
    body = section(read(stack), r"legal pages").lower()
    assert "existing route takes priority" in body, f"{stack}.md: Legal pages lacks the existing-route rule"
    assert "duplicate" in body, f"{stack}.md: Legal pages does not forbid duplicate policy pages"


def test_payload_groups_use_the_canonical_keys():
    """Every single-line consent payload in every file has exactly the canonical keys."""
    for stack in STACKS:
        for group in payload_groups(read(stack)):
            assert group_keys(group) == PAYLOAD_KEYS, f"{stack}.md: payload {group!r} deviates from {sorted(PAYLOAD_KEYS)}"


def test_consent_js_posts_the_canonical_payload():
    # The shared loader is the client for the Django, Laravel and Nest endpoints.
    groups = payload_groups(read("static-html"))
    sent = [g for g in groups if "VERSION" in g]
    assert sent, "static-html.md: consent.js JSON.stringify payload not found"
    for g in sent:
        assert group_keys(g) == PAYLOAD_KEYS


def test_django_form_and_test_match_consent_js():
    text = read("python")
    form = re.search(r"class ConsentEventForm\(forms\.Form\):(.*?)\n\n", text, re.S)
    assert form, "python.md: ConsentEventForm not found"
    fields = set(re.findall(r"^\s+(\w+) = forms\.", form.group(1), re.M))
    assert fields == PAYLOAD_KEYS, f"Django form fields {sorted(fields)} != consent.js payload"
    test_groups = [g for g in brace_groups(text) if g.lstrip("{ ").startswith('"subjectId"')]
    assert test_groups, "python.md: the Django test does not post a payload"
    for g in test_groups:
        assert group_keys(g) == PAYLOAD_KEYS


def test_nest_dto_matches_payload():
    text = read("nestjs")
    dto = re.search(r"class RecordConsentDto \{(.*?)\n\}", text, re.S)
    assert dto, "nestjs.md: RecordConsentDto not found"
    fields = set(re.findall(r"\)\s+(\w+): ", dto.group(1)))   # property after its decorators
    assert fields == PAYLOAD_KEYS, f"Nest DTO fields {sorted(fields)} != consent.js payload"


def test_laravel_validation_matches_payload():
    text = read("generic-web")
    rules = re.search(r"\$request->validate\(\[(.*?)\]\)", text, re.S)
    assert rules, "generic-web.md: Laravel validate() not found"
    keys = set(re.findall(r"'(\w+)' =>", rules.group(1)))
    assert keys == PAYLOAD_KEYS


@pytest.mark.parametrize("stack", STACKS)
def test_snake_case_never_used_as_a_json_key(stack):
    hit = SNAKE_JSON_KEY_RE.search(read(stack))
    assert hit is None, f"{stack}.md uses a snake_case key as a payload field: {hit.group(0)!r}"


def test_review_regressions():
    gw = read("generic-web")
    assert not re.search(r"\{#if[^}]*\}\s*<svelte:head>", gw), "svelte:head must not sit inside an {#if} block"
    assert "<svelte:head>{#if" in gw
    assert "!!e.checked" in read("nextjs"), "Chakra v3 handler must read e.checked"
    assert "@MainActor" in read("swift")
    nc = read("no-code")
    assert "woocommerce_register_additional_checkout_field" in nc and "ADMIN_SECTION" in nc
    assert "timestampTz" in gw
    assert ".catch(" in read("static-html")


def test_consent_js_logs_only_grants_and_revokes():
    js = read("static-html")
    assert "if (granted) log('grant')" in js and "if (revoked) log('revoke')" in js
    assert "log(granted ? 'grant' : 'revoke'" not in js, "a refusal must not be logged as a revoke"
    assert "remember(" not in js, "dead id logic for refusals must be gone"


def test_consent_js_waits_for_the_dom_and_guards_double_init():
    js = read("static-html")
    assert "DOMContentLoaded" in js, "banner lookup must wait for the DOM (inline paste in HEAD)"
    assert "once(" in js, "re-Accept must not init a counter twice"
    assert "getRandomValues" in js, "crypto.randomUUID is missing on plain-http pages"
    assert "gtm.js" in js


# --- second review round -----------------------------------------------------

STORED_VERSION_CHECKS = {
    "nextjs": "c.v === CONSENT_VERSION",
    "react": "c.v === CONSENT_VERSION",
    "static-html": "c.v === VERSION",
    "react-native": "c.v === CONSENT_VERSION",
    "flutter": "!= consentVersion",
    "swift": "== version",
}


@pytest.mark.parametrize("stack", sorted(STORED_VERSION_CHECKS))
def test_loader_code_checks_the_stored_version(stack):
    # Not only banner prose: the loader code must treat an old version as no choice.
    assert STORED_VERSION_CHECKS[stack] in read(stack), f"{stack}.md: loader does not compare the stored version"


@pytest.mark.parametrize("stack", ("nextjs", "react"))
def test_cookie_settings_link_keeps_the_stored_choice(stack):
    text = read(stack)
    assert "openConsentSettings" in text, f"{stack}.md: no reopen helper"
    assert "clears the stored value" not in text, f"{stack}.md: the footer link must not clear the stored choice"
    for needed in ("export function decide(", "const revoked", "logConsent('revoke')", "purgeCounterCookies()", "location.reload()"):
        assert needed in text, f"{stack}.md: decide() lacks {needed!r}"
    assert "it must not clear the stored choice" in text, f"{stack}.md: revoke bullet does not forbid clearing the choice"


def test_next_route_returns_400_on_invalid_json():
    assert "catch { return new Response(null, { status: 400 }); }" in read("nextjs")


def test_django_snippet_is_self_contained():
    text = read("python")
    assert 'CONSENT_TEXTS = {"1":' in text
    assert "from django.http import HttpResponse, HttpResponseBadRequest" in text
    for needed in ("import hashlib", "import json", "from .consent_texts import CONSENT_TEXTS", "from .models import ConsentLog"):
        assert needed in text, f"python.md: missing {needed!r}"


@pytest.mark.parametrize("stack", ("react-native", "flutter", "swift"))
def test_mobile_regrant_reenables_sending_and_revoke_is_consistent(stack):
    text = read(stack)
    assert "setDataSendingEnabled(on)" in text, f"{stack}.md: a re-grant in the same session never re-enables sending"
    assert "one per category" in text and "withdraw all" in text, f"{stack}.md: revoke semantics differ from the other mobile stacks"

