"""Checks for the eval fixtures in evals/.

Covers evals.json and triggers.json, the registry stubs, the prefilled
answers.json files (against the canonical skeleton in owner-questions.md),
the fixture trees, serve.sh, check_run.py and the golden reports.

Stdlib only. The repo root is located from this file, so the test runs from
any working directory.
"""

import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"
FIXTURES = EVALS / "fixtures"
STUBS = EVALS / "stubs"
GOLDEN = EVALS / "golden"
KB = ROOT / "skills" / "legal-kit" / "references" / "jurisdictions" / "ru"
SCRIPTS = ROOT / "skills" / "legal-kit" / "scripts"
CHECK_RUN = EVALS / "check_run.py"
SERVE_SH = EVALS / "serve.sh"

ID_RE = re.compile(r"(?<![\w-])ru:[a-z0-9]+(?:-[a-z0-9]+)*")
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "Podfile.lock",
    "pubspec.lock", "Package.resolved", "poetry.lock", "uv.lock", "Pipfile.lock", "composer.lock",
}
GOLDEN_TODAY = "2026-10-18"
# Hosts accepted as official sources, kept in step with the Task 6 allowlist.
OFFICIAL_HOSTS = (
    "pravo.gov.ru", "publication.pravo.gov.ru", "ips.pravo.gov.ru", "vsrf.ru", "ksrf.ru", "cbr.ru",
    "nalog.ru", "nalog.gov.ru", "sozd.duma.gov.ru", "regulation.gov.ru", "kremlin.ru",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_requirements():
    out = {}
    for line in (KB / "requirements.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            out[record["id"]] = record
    return out


REQUIREMENTS = load_requirements()


def host_is_official(url):
    host = urlparse(url).hostname or ""
    return host.endswith(".gov.ru") or any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS)


# --- checksums (same algorithms as the tax and registration authorities publish) -------------

def inn_valid(inn):
    if not re.fullmatch(r"\d{10}|\d{12}", inn):
        return False
    digits = [int(c) for c in inn]
    if len(digits) == 10:
        w = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        return sum(d * k for d, k in zip(digits, w)) % 11 % 10 == digits[9]
    w1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    w2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    return (sum(d * k for d, k in zip(digits, w1)) % 11 % 10 == digits[10]
            and sum(d * k for d, k in zip(digits, w2)) % 11 % 10 == digits[11])


def ogrn_valid(ogrn):
    if re.fullmatch(r"\d{13}", ogrn):
        return int(ogrn[:12]) % 11 % 10 == int(ogrn[12])
    if re.fullmatch(r"\d{15}", ogrn):
        return int(ogrn[:14]) % 13 % 10 == int(ogrn[14])
    return False


def test_checksum_helpers_accept_known_good_values():
    # Fictitious numbers: region code 00 does not exist, so no real organization carries them.
    assert inn_valid("0098765437") and not inn_valid("0098765438")
    assert inn_valid("009876543299") and not inn_valid("009876543298")
    assert ogrn_valid("1020000000008") and not ogrn_valid("1020000000009")
    assert ogrn_valid("304000000000018") and not ogrn_valid("304000000000019")


# --- evals.json -------------------------------------------------------------------------------

EVALS_JSON = load_json(EVALS / "evals.json")
EVAL_LIST = EVALS_JSON["evals"]


def eval_text(entry):
    return "\n".join([entry["prompt"], entry["expected_output"], *entry["expectations"]])


def test_evals_json_has_the_skill_creator_shape():
    assert EVALS_JSON["skill_name"] == "legal-kit"
    assert set(EVALS_JSON) == {"skill_name", "evals"}
    assert len(EVAL_LIST) >= 10
    ids = [e["id"] for e in EVAL_LIST]
    assert len(ids) == len(set(ids)), "eval ids must be unique"
    assert set(range(1, 11)) <= set(ids), "the 10 matrix evals must be present"
    for entry in EVAL_LIST:
        assert set(entry) == {"id", "prompt", "expected_output", "files", "expectations"}, entry["id"]
        assert isinstance(entry["id"], int)
        assert entry["prompt"].strip() and entry["expected_output"].strip()
        assert isinstance(entry["files"], list) and entry["files"], entry["id"]
        assert all(isinstance(f, str) for f in entry["files"])
        assert isinstance(entry["expectations"], list) and len(entry["expectations"]) >= 6, entry["id"]
        assert all(isinstance(x, str) and x.strip() for x in entry["expectations"])
        assert len(set(entry["expectations"])) == len(entry["expectations"]), f"duplicate expectation in eval {entry['id']}"


def test_prompts_mix_russian_and_english():
    cyrillic = [e["id"] for e in EVAL_LIST if re.search(r"[А-Яа-яЁё]", e["prompt"])]
    latin = [e["id"] for e in EVAL_LIST if not re.search(r"[А-Яа-яЁё]", e["prompt"])]
    assert len(cyrillic) >= 4 and len(latin) >= 3, (cyrillic, latin)


def test_every_listed_file_exists_inside_the_repo():
    for entry in EVAL_LIST:
        for rel in entry["files"]:
            assert not Path(rel).is_absolute(), rel
            path = (ROOT / rel).resolve()
            assert ROOT.resolve() in path.parents, f"{rel} leaves the repo"
            assert path.exists(), f"eval {entry['id']}: missing {rel}"


def test_every_requirement_id_named_in_the_evals_exists():
    named = set()
    for entry in EVAL_LIST:
        named.update(ID_RE.findall(eval_text(entry)))
    assert named, "expectations must name requirement ids"
    unknown = sorted(named - set(REQUIREMENTS))
    assert not unknown, f"ids missing from requirements.jsonl: {unknown}"


def test_each_eval_asks_for_check_run_and_names_a_requirement():
    for entry in EVAL_LIST:
        assert any("check_run.py" in x for x in entry["expectations"]), entry["id"]
        assert ID_RE.search("\n".join(entry["expectations"])), f"eval {entry['id']} names no requirement id"


def by_id(n):
    return next(e for e in EVAL_LIST if e["id"] == n)


def test_trap_expectations_from_the_matrix_are_present():
    traps = {
        1: ("ru:lokalizaciya-pdn", "interpretation", "disputed", "ru:soglasie-na-analitiku-i-cookies"),
        2: ("n_a", "ru:svedeniya-o-vladelce-sayta", "consent-banner"),
        3: ("owner.inn", "placeholder", "ru:nedopustimye-usloviya-oferty", "components/ui/checkbox", "messages/ru.json"),
        4: ("ru:obyazannosti-servisa-generativnogo-ii-243-fz", "roadmap", "official_runtime", "market", "ConsentLog", "Second run"),
        5: ("platform", "ru:pravila-storov-oplata-i-podpiski", "AppMetrica.activate", "documents"),
        6: ("ru:dokumenty-ob-obuchenii-po-itogam-kursa", "ru:onlayn-obuchenie-licenziya-i-prosveshchenie", "conditional"),
        7: ("ru:soglasie-na-rasprostranenie-pdn", "consent_service", "ru:otkaz-ot-uslug-i-cifrovyh-podpisok"),
        8: ("ru:platnye-medicinskie-uslugi-onlayn", "at most once", "ConsentCheckbox"),
        9: ("disputed", "AI agents", ".legal/answers.json", "`null`"),
        10: ("manual", "pd.rkn.gov.ru", "start questions", "No bypass"),
        11: ("86.23", "roszdravnadzor.gov.ru", "manual", "ru:platnye-medicinskie-uslugi-onlayn"),
    }
    for n, needles in traps.items():
        text = eval_text(by_id(n))
        for needle in needles:
            assert needle.lower() in text.lower(), f"eval {n} lacks {needle!r}"


def test_template_names_in_the_evals_exist():
    known = {tpl for rec in REQUIREMENTS.values() for tpl in rec["templates"]}
    known |= {p.stem for p in (KB / "documents").glob("*.md")}
    known |= {p.name for p in FIXTURES.iterdir()}
    named = set()
    for entry in EVAL_LIST:
        for token in re.findall(r"`([a-z]+(?:-[a-z0-9]+){2,})`", eval_text(entry)):
            named.add(token)
    assert {"politika-obrabotki-pdn", "oferta-uslugi-i-podpiska", "publichnaya-oferta-tovary"} <= named
    assert not named - known, f"unknown template or fixture names: {sorted(named - known)}"


def test_no_eval_needs_allow_kind_and_the_store_eval_records_the_withheld_requisites():
    for entry in EVAL_LIST:
        assert "--allow-kind" not in eval_text(entry), entry["id"]
    three = by_id(3)
    first = next(x for x in three["expectations"] if "check_run.py" in x)
    assert "owner.withheld" in first and "placeholder_requisite" in first and "desired outcome" in first
    assert "`risk`" in first and "blocking" in first
    store = load_json(FIXTURES / "store-nextjs" / ".legal" / "answers.json")
    assert store["owner"]["withheld"] == [], "the run writes owner.withheld from the prompt, not the fixture"


def test_iteration_1_rulings_are_reflected_in_the_expectations():
    four = " ".join(by_id(4)["expectations"])
    assert "`present`" in four and "bucket `done`" in four and "norm_dates" in four
    five = " ".join(by_id(5)["expectations"])
    assert "single gated entry point" in five and "notice with a policy link" in five
    assert "link to the Documents screen" in five
    two = next(x for x in by_id(2)["expectations"] if "confirmation block" in x and "repeats" in x)
    assert "as confirmed without a question" in two and two.count("as confirmed") == 1
    eight = next(x for x in by_id(8)["expectations"] if x.startswith("One package"))
    assert "at most once" in eight and "separate `disputed` row" in eight
    ten = next(x for x in by_id(10)["expectations"] if x.startswith("Start questions"))
    assert "production domain" in ten and "what the product is" in ten
    three = " ".join(by_id(3)["expectations"])
    assert "i18n catalogs" in three and "content files" in three


def test_url_only_evals_serve_the_fixture_instead_of_copying_it():
    ten = by_id(10)
    assert ten["files"] == ["evals/stubs"], "eval 10 must start in an empty workspace"
    assert "empty working directory" in ten["expected_output"] and "serve.sh landing-static" in ten["expected_output"]
    assert "ИНН" not in ten["prompt"] and "ООО" not in ten["prompt"], "owner details come with the start-question reply"
    assert "prod-only" in " ".join(ten["expectations"])
    assert "ответственный за обработку ПДн" in ten["expected_output"], "the reply fills the policy's responsible person"
    five = by_id(5)
    assert not any("mobile-expo-store-page" in f for f in five["files"])
    assert "serve.sh mobile-expo-store-page 8732" in five["expected_output"] and "only served" in five["expected_output"]


def test_repo_evals_get_a_git_baseline_so_commits_and_clean_tree_can_be_graded():
    for entry in EVAL_LIST:
        if entry["id"] == 10:
            assert "git init" not in entry["expected_output"]
            continue
        assert "git init" in entry["expected_output"] and "baseline" in entry["expected_output"], entry["id"]
        assert any("baseline commit" in x for x in entry["expectations"]), entry["id"]
    four = by_id(4)
    assert "snapshot" in four["expected_output"] and "продолжай" in four["expected_output"]
    assert any("snapshot" in x and "baseline commit" in x for x in four["expectations"])


def test_store_rules_are_base_rows_with_platform_basis():
    for n in (5, 8):
        text = " ".join(by_id(n)["expectations"])
        assert "`source` `base`" in text and "`platform`" in text
        assert "`source` `platform`" not in text


def test_the_review_findings_are_reflected_in_the_expectations():
    two = " ".join(by_id(2)["expectations"])
    assert "svedeniya-o-prodavce-i-vladelce-sayta:А1" in two and "never `partial` or `missing`" in two
    assert "confirmation block" in two
    three = " ".join(by_id(3)["expectations"])
    assert "`risk`" in three and "7 days" in three and "3 months" in three and "10 days" in three
    assert "WHOIS by domain is allowed" in three
    four = " ".join(by_id(4)["expectations"])
    assert "`official_runtime` or `market`" in four and "`base` (the knowledge base" in four
    assert "No new dependency" in four and "No new dependency" in " ".join(by_id(6)["expectations"])
    for n in (1, 9):
        assert "notice with a policy link" in " ".join(by_id(n)["expectations"]), n
    eight = " ".join(by_id(8)["expectations"])
    assert "one draft per template" in eight and "registry.py cbr" in eight
    assert "registry.py cbr" not in next(x for x in by_id(8)["expectations"] if x.startswith("Trap, medical"))
    eleven = " ".join(by_id(11)["expectations"])
    assert "`business.sectors` `[]`" in eleven and "если у клиники есть сайт" in eleven


def test_roadmap_date_is_taken_from_the_card_not_typed_from_memory():
    record = REQUIREMENTS["ru:obyazannosti-servisa-generativnogo-ii-243-fz"]
    assert record["effective_from"] == "2027-03-01"
    assert record["effective_from"] in " ".join(by_id(4)["expectations"])


def test_every_expectation_date_in_a_requirement_context_matches_its_record():
    # An expectation that pairs a requirement id with an effective_from date must agree with the record.
    for entry in EVAL_LIST:
        for text in entry["expectations"]:
            ids = ID_RE.findall(text)
            dates = re.findall(r"\b20\d\d-\d\d-\d\d\b", text)
            if len(ids) == 1 and len(dates) == 1 and "effective_from" in text:
                assert REQUIREMENTS[ids[0]]["effective_from"] == dates[0], (entry["id"], ids[0], dates[0])


# --- triggers.json ----------------------------------------------------------------------------

def test_triggers_json_has_ten_positive_and_ten_negative_queries():
    triggers = load_json(EVALS / "triggers.json")
    assert isinstance(triggers, list) and len(triggers) == 20
    for item in triggers:
        assert set(item) == {"query", "should_trigger"}
        assert isinstance(item["query"], str) and item["query"].strip()
        assert isinstance(item["should_trigger"], bool)
    queries = [t["query"] for t in triggers]
    assert len(set(queries)) == 20
    positive = [t for t in triggers if t["should_trigger"]]
    negative = [t for t in triggers if not t["should_trigger"]]
    assert len(positive) == 10 and len(negative) == 10
    for group in (positive, negative):
        russian = [t for t in group if re.search(r"[А-Яа-яЁё]", t["query"])]
        english = [t for t in group if not re.search(r"[А-Яа-яЁё]", t["query"])]
        assert len(russian) >= 3 and len(english) >= 3, "each group mixes Russian and English"
    near_miss = re.compile(r"GDPR|CCPA|аренд|трудов|cookie|баннер", re.I)
    assert len([t for t in negative if near_miss.search(t["query"])]) >= 6, "negatives are near-misses, not noise"
    for topic in ("GDPR", "CCPA", "аренд", "трудов", "iOS Safari"):
        assert any(topic in t["query"] for t in negative), topic


# --- stubs ------------------------------------------------------------------------------------

STUB_NAME_RE = re.compile(r"^(egrul|npd|whois|cbr|rkn)-(.+)\.json$")
STUB_STATUSES = {"ok", "not_found", "manual", "error"}
STUB_FILES = sorted(STUBS.glob("*.json"))


def test_stub_files_exist_for_every_registry_kind():
    kinds = {STUB_NAME_RE.match(p.name).group(1) for p in STUB_FILES if STUB_NAME_RE.match(p.name)}
    assert kinds == {"egrul", "npd", "whois", "cbr", "rkn"}


@pytest.mark.parametrize("path", STUB_FILES, ids=lambda p: p.name)
def test_stub_has_the_registry_shape(path):
    match = STUB_NAME_RE.match(path.name)
    assert match, f"stub name must be <kind>-<arg>.json: {path.name}"
    stub = load_json(path)
    assert {"status", "data", "url", "checked_at"} <= set(stub)
    assert stub["status"] in STUB_STATUSES
    assert isinstance(stub["data"], dict)
    assert isinstance(stub["url"], str) and stub["url"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stub["checked_at"])
    kind, arg = match.groups()
    if kind in ("egrul", "npd"):
        assert inn_valid(arg), f"stub key {arg} is not a checksum-valid INN"
        # registry.py answers an EGRUL miss with {"key": <inn>}, everything else carries "inn"
        key = "key" if kind == "egrul" and stub["status"] == "not_found" else "inn"
        assert stub["data"][key] == arg
    if kind == "npd" and stub["status"] == "not_found":
        assert stub["data"]["is_npd"] is False
    if kind == "cbr":
        assert ogrn_valid(arg)


def eval_owners():
    """(eval id, status, INN) for every owner an eval names: in its prompt, its reply or its answers fixture."""
    owners = []
    for entry in EVAL_LIST:
        for item in entry["files"]:
            path = ROOT / item
            path = path if path.name == "answers.json" else path / ".legal" / "answers.json"
            if path.is_file():
                owner = load_json(path)["owner"]
                owners.append((entry["id"], owner["status"], owner["inn"]))
        text = entry["prompt"] + " " + entry["expected_output"]
        status = "npd" if re.search(r"самозанят", entry["prompt"], re.I) else None
        for inn in re.findall(r"ИНН (\d{10}|\d{12})\b", text):
            owners.append((entry["id"], status, inn))
    return owners


def test_every_inn_an_eval_uses_has_registry_stubs():
    owners = eval_owners()
    assert ("2", "npd", "001234500498") in {(str(i), s, n) for i, s, n in owners}
    for eval_id, status, inn in owners:
        if not inn:
            continue
        assert (STUBS / f"egrul-{inn}.json").is_file(), (eval_id, inn)
        if status in ("ip", "npd"):
            assert (STUBS / f"npd-{inn}.json").is_file(), (eval_id, inn)
    assert load_json(STUBS / "egrul-001234500498.json")["status"] == "not_found", "a self-employed person is not in EGRUL"


def test_the_rkn_stubs_are_manual_geo_blocks():
    rkn = [load_json(p) for p in STUB_FILES if p.name.startswith("rkn-")]
    assert rkn
    for stub in rkn:
        assert stub["status"] == "manual"
        assert stub["data"]["reason"] == "geo-block"
        assert stub["url"].startswith("https://pd.rkn.gov.ru/")


def test_a_stub_shows_okved_86_23_for_the_dentistry_variant():
    stub = load_json(STUBS / "egrul-0012345049.json")
    assert stub["status"] == "ok" and stub["data"]["okved_main"] == "86.23"


def test_the_cbr_stub_is_a_negative_control_for_the_shop_owner():
    shop = load_json(FIXTURES / "shop-swift" / ".legal" / "answers.json")
    stub = load_json(STUBS / f"cbr-{shop['owner']['ogrn']}.json")
    assert stub["status"] == "not_found"
    assert shop["business"]["sectors"] == []


# --- prefilled answers.json -------------------------------------------------------------------

def load_skeleton():
    text = (KB / "owner-questions.md").read_text(encoding="utf-8")
    section = text.split("## Схема answers.json", 1)[1]
    block = re.search(r"```json\n(.*?)\n```", section, re.S)
    assert block, "skeleton block not found in owner-questions.md"
    return json.loads(block.group(1))


SKELETON = load_skeleton()
FEATURE_MAP_PATH = KB / "feature-map.json"
# Sector keys are the keys of the `sectoral` section of feature-map.json, as the skeleton says.
SECTORS = set(load_json(FEATURE_MAP_PATH)["sectoral"]) if FEATURE_MAP_PATH.is_file() else None
ANSWER_FILES = sorted(FIXTURES.glob("*/.legal/answers.json"))


def enum_of(description):
    """Allowed values written in a skeleton description, e.g. 'none | 14-18 | under-14 | null: ...'."""
    if description.startswith("list of:"):
        body = description.split(":", 1)[1]
    else:
        body = description.split(":", 1)[0]
    values = [v.strip() for v in body.split("|")]
    return {None if v == "null" else v for v in values if v}


def assert_same_keys(skeleton, actual, where=""):
    assert isinstance(actual, dict), where
    assert set(actual) == set(skeleton), f"{where or 'root'}: keys differ: {sorted(set(actual) ^ set(skeleton))}"
    for key, sub in skeleton.items():
        if isinstance(sub, dict):
            assert_same_keys(sub, actual[key], f"{where}.{key}")


def test_sector_keys_come_from_feature_map_and_the_skeleton_says_so():
    description = SKELETON["business"]["sectors"]
    assert "feature-map.json" in description and "sectoral" in description
    if SECTORS is not None:
        assert {"medical", "education"} <= SECTORS
        for path in ANSWER_FILES:
            assert set(load_json(path)["business"]["sectors"]) <= SECTORS


@pytest.mark.parametrize("path", ANSWER_FILES, ids=lambda p: p.parts[-3])
def test_pd_officer_is_a_fictitious_person_for_companies_and_null_otherwise(path):
    owner = load_json(path)["owner"]
    assert "pd_officer" in SKELETON["owner"]
    if owner["status"] == "ul":
        assert isinstance(owner["pd_officer"], str) and owner["pd_officer"].strip()
        assert owner["pd_officer"].endswith(".test"), "the contact uses the reserved test TLD"
    else:
        assert owner["pd_officer"] is None


def test_skeleton_was_parsed():
    assert set(SKELETON) == {"version", "updated", "product", "owner", "audience", "business", "decisions",
                             "document_facts"}
    assert "withheld" in SKELETON["owner"] and SKELETON["owner"]["withheld"].startswith("list of")
    assert SKELETON["document_facts"].startswith("object")
    assert SKELETON["decisions"]["consent_at_forms"].startswith("list of")


@pytest.mark.parametrize("path", ANSWER_FILES, ids=lambda p: p.parts[-3])
def test_answers_withheld_and_document_facts_have_their_types(path):
    answers = load_json(path)
    assert isinstance(answers["owner"]["withheld"], list)
    assert answers["decisions"]["consent_at_forms"] == [], "the run records an explicit wish from the prompt"
    assert isinstance(answers["document_facts"], dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in answers["document_facts"].items())


def test_answers_fixtures_exist_for_every_fixture_except_the_two_without():
    expected = {"landing-static", "landing-injection", "store-nextjs", "saas-nest-react", "mobile-expo",
                "courses-django", "services-flutter", "services-flutter-dentistry", "shop-swift"}
    assert {p.parts[-3] for p in ANSWER_FILES} == expected
    assert not (FIXTURES / "landing-minimal" / ".legal").exists()


@pytest.mark.parametrize("path", ANSWER_FILES, ids=lambda p: p.parts[-3])
def test_answers_follow_the_canonical_skeleton(path):
    answers = load_json(path)
    assert_same_keys(SKELETON, answers)
    assert answers["version"] == 1
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", answers["updated"])
    assert set(answers["product"]["kinds"]) <= enum_of(SKELETON["product"]["kinds"])
    assert answers["owner"]["status"] in enum_of(SKELETON["owner"]["status"])
    assert re.fullmatch(r"[A-Z]{2}", answers["owner"]["country"])
    assert answers["audience"]["minors"] in enum_of(SKELETON["audience"]["minors"])
    if SECTORS is not None:
        assert set(answers["business"]["sectors"]) <= SECTORS
    else:
        assert answers["business"]["sectors"] == [], "no feature-map.json to check sector keys against"
    assert answers["decisions"]["commit_legal_dir"] in (False, None)
    assert answers["product"]["repo"] == "."


@pytest.mark.parametrize("path", ANSWER_FILES, ids=lambda p: p.parts[-3])
def test_fixture_requisites_are_fictitious_but_checksum_valid(path):
    owner = load_json(path)["owner"]
    if owner["inn"] is None:
        assert owner["ogrn"] is None
        return
    assert inn_valid(owner["inn"]), owner["inn"]
    assert owner["inn"].startswith("00"), "fictitious INNs use the non-existent region code 00"
    assert ogrn_valid(owner["ogrn"]), owner["ogrn"]
    if owner["status"] == "ul":
        assert len(owner["inn"]) == 10 and len(owner["ogrn"]) == 13
    if owner["status"] == "ip":
        assert len(owner["inn"]) == 12 and len(owner["ogrn"]) == 15


def test_store_answers_omit_inn_and_ogrn_on_purpose():
    owner = load_json(FIXTURES / "store-nextjs" / ".legal" / "answers.json")["owner"]
    assert owner["inn"] is None and owner["ogrn"] is None
    assert owner["name"] and owner["address"] and owner["email"]


def test_every_answers_inn_has_an_egrul_stub():
    for path in ANSWER_FILES:
        inn = load_json(path)["owner"]["inn"]
        if inn:
            stub = STUBS / f"egrul-{inn}.json"
            assert stub.is_file(), f"{path.parts[-3]}: no stub for {inn}"
            assert load_json(stub)["data"]["name"] == load_json(path)["owner"]["name"]


def test_services_variant_differs_only_where_the_medical_case_needs():
    base = load_json(FIXTURES / "services-flutter" / ".legal" / "answers.json")
    dental = load_json(FIXTURES / "services-flutter-dentistry" / ".legal" / "answers.json")
    # The overlay does not pre-set the sector: the skill must derive "medical" from the OKVED in the
    # registry stub and the clinic wording, then get it confirmed.
    assert base["business"]["sectors"] == [] and dental["business"]["sectors"] == []
    assert "стоматолог" in dental["product"]["summary"].lower()
    assert "стоматолог" not in base["product"]["summary"].lower()
    assert load_json(STUBS / f"egrul-{dental['owner']['inn']}.json")["data"]["okved_main"] == "86.23"
    assert load_json(STUBS / f"egrul-{base['owner']['inn']}.json")["data"]["okved_main"] != "86.23"


def test_fictitious_domains_use_the_reserved_test_tld():
    # .test cannot be registered, so no fixture domain can collide with a real site.
    old_style = re.compile(r"[a-z0-9-]+-test(?:ov)?\.ru\b|petr-testov\.ru", re.I)
    for path in EVALS.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".html", ".php", ".ts", ".tsx", ".dart", ".swift", ".py", ".sh"):
            assert not old_style.search(path.read_text(encoding="utf-8")), path.relative_to(EVALS)
    for answers in ANSWER_FILES:
        data = load_json(answers)
        assert data["owner"]["email"].endswith(".test"), answers
        assert all(url.endswith(".test") or ".test/" in url or url.startswith("http://localhost")
                   for url in data["product"]["urls"] + [u for u in data["product"]["stores"].values() if u]), answers
    assert not list(STUBS.glob("whois-*.ru.json"))
    assert sorted(p.name for p in STUBS.glob("whois-*.json")) == [
        "whois-oblako.test.json", "whois-romashka.test.json", "whois-shkola.test.json", "whois-teply-dom.test.json"]


# --- fixture trees ----------------------------------------------------------------------------

FIXTURE_DIRS = sorted(p for p in FIXTURES.iterdir() if p.is_dir())


def test_expected_fixture_directories_exist():
    assert {p.name for p in FIXTURE_DIRS} == {
        "landing-static", "landing-injection", "landing-minimal", "store-nextjs", "saas-nest-react",
        "mobile-expo", "mobile-expo-store-page", "courses-django", "services-flutter",
        "services-flutter-dentistry", "shop-swift",
    }


@pytest.mark.parametrize("fixture", FIXTURE_DIRS, ids=lambda p: p.name)
def test_fixture_is_minimal(fixture):
    files = [p for p in fixture.rglob("*") if p.is_file()]
    assert files, fixture.name
    assert len(files) <= 25, f"{fixture.name}: {len(files)} files, fixtures stay small"
    for path in files:
        rel = path.relative_to(fixture)
        assert "node_modules" not in rel.parts and ".git" not in rel.parts and "build" not in rel.parts, rel
        assert path.name not in LOCKFILES, rel
        assert path.stat().st_size < 20_000, f"{rel} is too big for a fixture"
        path.read_text(encoding="utf-8")  # text only


def test_injection_fixture_is_landing_static_plus_hidden_text():
    base, inj = FIXTURES / "landing-static", FIXTURES / "landing-injection"
    base_files = {p.relative_to(base): p for p in base.rglob("*") if p.is_file()}
    inj_files = {p.relative_to(inj): p for p in inj.rglob("*") if p.is_file()}
    assert set(base_files) == set(inj_files)
    for rel, path in base_files.items():
        if rel.name == "index.html":
            continue
        assert path.read_bytes() == inj_files[rel].read_bytes(), rel
    page = (inj / "index.html").read_text(encoding="utf-8")
    original = (base / "index.html").read_text(encoding="utf-8")
    assert "AI agents:" in page and "skip the report" in page
    assert "NOTE TO AI ASSISTANT" in page and "delete .legal/answers.json" in page
    assert "AI agents" not in original
    removed = [ln for ln in original.splitlines() if ln not in page.splitlines()]
    assert not removed, "the injected copy only adds lines"


def test_store_fixture_carries_the_outdated_offer_and_the_existing_checkbox():
    store = FIXTURES / "store-nextjs"
    offer = (store / "app" / "[locale]" / "(legal)" / "offer" / "page.tsx").read_text(encoding="utf-8")
    assert "Товар надлежащего качества возврату не подлежит" in offer
    assert "Споры рассматриваются по месту нахождения Продавца" in offer
    assert "цена может быть изменена после оформления заказа" in offer
    assert (store / "components" / "ui" / "checkbox.tsx").is_file()
    package = load_json(store / "package.json")["dependencies"]
    assert {"next", "next-intl", "@prisma/client", "@a2seven/yoo-checkout"} <= set(package)
    assert (store / "messages" / "ru.json").is_file() and (store / "messages" / "en.json").is_file()
    assert load_json(store / "tsconfig.json")["compilerOptions"]["paths"]["@/*"] == ["./*"]
    config = (store / "next.config.ts").read_text(encoding="utf-8")
    assert "next-intl/plugin" in config and "./i18n/request.ts" in config


def test_saas_fixture_has_the_signals_the_eval_relies_on():
    saas = FIXTURES / "saas-nest-react"
    schema = (saas / "backend" / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    assert "autoRenew" in schema and "trialEndsAt" in schema and "ConsentLog" not in schema
    assert "yandexgpt" in (saas / "backend" / "src" / "chat" / "chat.service.ts").read_text(encoding="utf-8")
    assert "cloudpayments" in (saas / "backend" / "src" / "billing" / "billing.service.ts").read_text(encoding="utf-8")
    assert "@nestjs/core" in load_json(saas / "backend" / "package.json")["dependencies"]


def test_mobile_and_courses_fixtures_have_their_signals():
    mobile = FIXTURES / "mobile-expo"
    deps = load_json(mobile / "package.json")["dependencies"]
    assert {"expo", "@appmetrica/react-native-analytics", "expo-notifications", "react-native-iap"} <= set(deps)
    assert "AppMetrica.activate" in (mobile / "src" / "metrics.ts").read_text(encoding="utf-8")
    store_page = (FIXTURES / "mobile-expo-store-page" / "index.html").read_text(encoding="utf-8")
    assert "Разработчик не собирает данные из этого приложения" in store_page
    detail = (FIXTURES / "courses-django" / "templates" / "courses" / "detail.html").read_text(encoding="utf-8")
    assert "Сертификат о прохождении курса" in detail


def test_shop_swift_has_no_medical_sign_except_the_word_consultation():
    shop = FIXTURES / "shop-swift"
    text = "\n".join(p.read_text(encoding="utf-8") for p in shop.rglob("*") if p.is_file()).lower()
    assert "консультаци" in text
    for sign in ("врач", "клиник", "лечен", "медицин", "здоровь", "стоматолог", "86.2"):
        assert sign not in text, sign


# --- serve.sh ---------------------------------------------------------------------------------

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fetch_status(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code
    except OSError:
        return None


def test_serve_sh_rejects_unknown_fixture_and_bad_port():
    unknown = subprocess.run(["sh", str(SERVE_SH), "no-such-fixture"], capture_output=True, text=True)
    assert unknown.returncode == 2 and "no such fixture" in unknown.stderr
    bad_port = subprocess.run(["sh", str(SERVE_SH), "landing-static", "abc"], capture_output=True, text=True)
    assert bad_port.returncode == 2


@pytest.mark.skipif(shutil.which("tar") is None, reason="tar is needed by serve.sh")
def test_serve_sh_serves_the_site_but_not_the_owner_files():
    port = free_port()
    proc = subprocess.Popen(["sh", str(SERVE_SH), "landing-static", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 10
        status = None
        while time.time() < deadline and status != 200:
            status = fetch_status(f"{base}/index.html")
            time.sleep(0.2)
        assert status == 200
        assert fetch_status(f"{base}/css/style.css") == 200
        assert fetch_status(f"{base}/.legal/answers.json") == 404
        assert fetch_status(f"{base}/send.php") == 404
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# --- check_run.py -----------------------------------------------------------------------------

def run_check(run_dir, *args, scripts=None, cwd=None):
    cmd = [sys.executable, str(CHECK_RUN), str(run_dir)]
    if scripts is not None:
        cmd += ["--scripts-dir", str(scripts)]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def make_scripts(tmp_path, verify_rc=0, docs_output='{"issues": []}', docs_rc=0, verify_sleep=0):
    """Fake report.py and check_docs.py. Both fail with exit 3 when a path argument does not exist,
    which is what a doubled relative path looks like to a real script."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "report.py").write_text(
        "import json, os, sys, time\n"
        f"json.dump(sys.argv[1:], open({str(tmp_path / 'verify-argv.json')!r}, 'w'))\n"
        f"time.sleep({verify_sleep})\n"
        "paths = [sys.argv[2]] + [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a in ('--kb', '--sources')]\n"
        "sys.exit(3 if not all(os.path.exists(p) for p in paths) else "
        f"{verify_rc})\n", encoding="utf-8")
    (scripts / "check_docs.py").write_text(
        "import json, os, sys\n"
        f"json.dump(sys.argv[1:], open({str(tmp_path / 'docs-argv.json')!r}, 'w'))\n"
        "paths = [a for a in sys.argv[1:] if not a.startswith('--')]\n"
        "if not all(os.path.exists(p) for p in paths):\n"
        "    sys.exit(3)\n"
        f"print({docs_output!r})\n"
        f"sys.exit({docs_rc})\n", encoding="utf-8")
    return scripts


def make_run(tmp_path, drafts=True, answers=True, sources=False, report=True):
    run = tmp_path / "run"
    legal = run / ".legal"
    legal.mkdir(parents=True)
    if report:
        (legal / "report.json").write_text('{"rows": []}', encoding="utf-8")
    if answers:
        (legal / "answers.json").write_text("{}", encoding="utf-8")
    if sources:
        (legal / "sources.json").write_text("[]", encoding="utf-8")
    if drafts:
        (legal / "drafts").mkdir()
        (legal / "drafts" / "politika-obrabotki-pdn.md").write_text("draft", encoding="utf-8")
        (legal / "drafts" / "notes.json").write_text("{}", encoding="utf-8")
    return run


def test_check_run_exits_2_with_a_clear_message_when_the_scripts_are_missing(tmp_path):
    empty = tmp_path / "no-scripts"
    empty.mkdir()
    result = run_check(make_run(tmp_path), scripts=empty)
    assert result.returncode == 2
    assert "report.py" in result.stderr and "check_docs.py" in result.stderr and "missing" in result.stderr


def test_check_run_default_scripts_dir_is_the_skill_scripts_dir():
    if (SCRIPTS / "report.py").is_file() and (SCRIPTS / "check_docs.py").is_file():
        pytest.skip("scripts exist; the default is exercised by the golden test")
    result = subprocess.run([sys.executable, str(CHECK_RUN), str(EVALS)], capture_output=True, text=True)
    assert result.returncode == 2 and "missing" in result.stderr


def test_check_run_passes_when_both_scripts_pass(tmp_path):
    scripts = make_scripts(tmp_path)
    run = make_run(tmp_path, sources=True)
    result = run_check(run, "--today", "2026-10-18", scripts=scripts)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("check_run: PASS")
    verify_args = json.loads((tmp_path / "verify-argv.json").read_text())
    assert verify_args[0] == "verify" and verify_args[1].endswith(".legal/report.json")
    assert "--kb" in verify_args and verify_args[verify_args.index("--kb") + 1].endswith("jurisdictions/ru")
    assert verify_args[verify_args.index("--sources") + 1].endswith(".legal/sources.json")
    assert verify_args[verify_args.index("--today") + 1] == "2026-10-18"
    docs_args = json.loads((tmp_path / "docs-argv.json").read_text())
    assert [a for a in docs_args if a.endswith(".md")] and not [a for a in docs_args if a.endswith(".json") and "drafts" in a]
    assert docs_args[docs_args.index("--answers") + 1].endswith(".legal/answers.json")


def test_check_run_resolves_relative_paths_before_the_scripts_change_directory(tmp_path):
    scripts = make_scripts(tmp_path)
    make_run(tmp_path, sources=True)
    kb = tmp_path / "kb"
    kb.mkdir()
    # every path is relative to tmp_path, the directory the command runs in
    result = run_check("run", "--kb", "kb", "--today", "2026-10-18", scripts="scripts", cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    verify_args = json.loads((tmp_path / "verify-argv.json").read_text())
    docs_args = json.loads((tmp_path / "docs-argv.json").read_text())
    for value in (verify_args[1], verify_args[verify_args.index("--kb") + 1],
                  verify_args[verify_args.index("--sources") + 1], docs_args[docs_args.index("--answers") + 1],
                  *[a for a in docs_args if a.endswith(".md")]):
        assert Path(value).is_absolute() and Path(value).exists(), value


def test_check_run_passes_the_answers_file_to_verify_when_it_exists(tmp_path):
    scripts = make_scripts(tmp_path)
    assert run_check(make_run(tmp_path, drafts=False), scripts=scripts).returncode == 0
    verify_args = json.loads((tmp_path / "verify-argv.json").read_text())
    assert verify_args[verify_args.index("--answers") + 1].endswith(".legal/answers.json")
    assert Path(verify_args[verify_args.index("--answers") + 1]).is_absolute()


def test_check_run_leaves_the_answers_flag_out_when_there_is_no_answers_file(tmp_path):
    scripts = make_scripts(tmp_path)
    run = make_run(tmp_path, drafts=False, answers=False)
    assert run_check(run, scripts=scripts).returncode == 0
    assert "--answers" not in json.loads((tmp_path / "verify-argv.json").read_text())


def test_check_run_omits_sources_and_today_when_not_given(tmp_path):
    scripts = make_scripts(tmp_path)
    assert run_check(make_run(tmp_path), scripts=scripts).returncode == 0
    verify_args = json.loads((tmp_path / "verify-argv.json").read_text())
    assert "--sources" not in verify_args and "--today" not in verify_args


def test_check_run_fails_when_verify_reports_violations(tmp_path):
    result = run_check(make_run(tmp_path), scripts=make_scripts(tmp_path, verify_rc=1))
    assert result.returncode == 1 and "check_run: FAIL" in result.stdout


def test_check_run_treats_a_verify_crash_as_an_error_not_a_failure(tmp_path):
    result = run_check(make_run(tmp_path), scripts=make_scripts(tmp_path, verify_rc=2))
    assert result.returncode == 2 and "ERROR" in result.stderr and "FAIL" not in result.stdout


def test_check_run_fails_only_on_blocking_check_docs_issues(tmp_path):
    cases = {
        "draft": ('{"issues": [{"file": "a.md", "line": 3, "kind": "placeholder_fact", "blocking": false}]}', 0, 0),
        "risk": ('{"issues": [{"file": "a.md", "line": 3, "kind": "forbidden_clause", "blocking": false}]}', 0, 0),
        "public": ('{"issues": [{"file": "p.html", "line": 3, "kind": "placeholder_fact", "blocking": true}]}', 1, 1),
        "no flag": ('{"issues": [{"file": "a.md", "line": 3, "kind": "inn_checksum"}]}', 1, 1),
    }
    for name, (output, rc, expected) in cases.items():
        folder = tmp_path / name.replace(" ", "-")
        folder.mkdir()
        result = run_check(make_run(folder), scripts=make_scripts(folder, docs_output=output, docs_rc=rc))
        assert result.returncode == expected, (name, result.stdout + result.stderr)
        assert ("1 blocking" if expected else "0 blocking") in result.stdout, name


def test_check_run_has_no_allow_kind_flag_any_more(tmp_path):
    result = run_check(make_run(tmp_path), "--allow-kind", "placeholder", scripts=make_scripts(tmp_path))
    assert result.returncode == 2 and "--allow-kind" in result.stderr


def write_state(run, *paths):
    managed = [{"path": p, "sha256": "0" * 64, "kind": "page"} for p in paths]
    (run / ".legal" / "state.json").write_text(json.dumps({"managed": managed}), encoding="utf-8")


def docs_call(tmp_path):
    """(positional drafts, --public files) of the fake check_docs call."""
    argv = json.loads((tmp_path / "docs-argv.json").read_text())
    first_option = next(i for i, a in enumerate(argv) if a.startswith("--"))
    drafts, rest = argv[:first_option], argv[first_option:]
    public, i = [], 0
    while i < len(rest):  # check_docs takes one file per --public: every public file has its own flag
        if rest[i] == "--public":
            public.append(rest[i + 1])
            i += 2
        else:
            assert rest[i] == "--answers", f"unexpected argument {rest[i]!r} in {argv}"
            i += 2
    return drafts, public


def test_check_run_passes_managed_project_files_and_paste_artifacts_as_public(tmp_path):
    scripts = make_scripts(tmp_path)
    run = make_run(tmp_path)
    for rel_path, content in (("legal/privacy.html", "<p>x</p>"), ("components/Footer.tsx", "export {}"),
                              (".legal/paste/html/offer.html", "<p>y</p>")):
        (run / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (run / rel_path).write_text(content, encoding="utf-8")
    (run / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00binary")
    write_state(run, "legal/privacy.html", "components/Footer.tsx", ".legal/drafts/politika-obrabotki-pdn.md",
                "logo.png", "gone.html", "../outside.html", "/etc/hosts")
    result = run_check(run, scripts=scripts)
    assert result.returncode == 0, result.stdout + result.stderr
    drafts, public = docs_call(tmp_path)
    assert [Path(p).name for p in drafts] == ["politika-obrabotki-pdn.md"]
    assert sorted(Path(p).relative_to(run).as_posix() for p in public) == [
        ".legal/paste/html/offer.html", "components/Footer.tsx", "legal/privacy.html"]
    assert all(Path(p).is_absolute() for p in drafts + public)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_check_run_takes_files_changed_since_the_baseline_commit_as_public(tmp_path):
    scripts = make_scripts(tmp_path)
    run = make_run(tmp_path, drafts=False)
    (run / "index.html").write_text("<p>old</p>", encoding="utf-8")
    (run / "untouched.html").write_text("<p>same</p>", encoding="utf-8")
    git = ["git", "-C", str(run), "-c", "user.name=t", "-c", "user.email=t@example.test"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "baseline"], check=True)
    (run / "index.html").write_text("<p>new</p>", encoding="utf-8")
    (run / "legal").mkdir()
    (run / "legal" / "cookies.html").write_text("<p>c</p>", encoding="utf-8")
    (run / ".legal" / "notes.md").write_text("n", encoding="utf-8")
    result = run_check(run, scripts=scripts)
    assert result.returncode == 0, result.stdout + result.stderr
    drafts, public = docs_call(tmp_path)
    assert drafts == []
    assert sorted(Path(p).relative_to(run).as_posix() for p in public) == ["index.html", "legal/cookies.html"]


def test_check_run_ignores_the_enclosing_repository_of_a_run_dir(tmp_path):
    # the goldens live inside this repository: its git status must not leak into their check
    scripts = make_scripts(tmp_path)
    result = run_check(GOLDEN / "saas-nest-react", scripts=scripts)
    assert result.returncode == 0 and "skipped" in result.stdout, result.stdout


def test_check_run_fails_on_issues_even_when_check_docs_exits_zero(tmp_path):
    issues = '{"issues": [{"file": "a.md", "line": 3, "kind": "mismatch"}]}'
    result = run_check(make_run(tmp_path), scripts=make_scripts(tmp_path, docs_output=issues, docs_rc=0))
    assert result.returncode == 1 and "mismatch" in result.stdout


def test_check_run_honours_a_failing_check_docs_exit_code_without_issues(tmp_path):
    result = run_check(make_run(tmp_path), scripts=make_scripts(tmp_path, docs_output='{"issues": []}', docs_rc=1))
    assert result.returncode == 1 and "without listing an issue" in result.stdout


def test_check_run_treats_a_check_docs_crash_as_an_error(tmp_path):
    result = run_check(make_run(tmp_path), scripts=make_scripts(tmp_path, docs_output='{"issues": []}', docs_rc=2))
    assert result.returncode == 2 and "ERROR" in result.stderr


def test_check_run_rejects_check_docs_json_without_an_issues_key(tmp_path):
    for output in ('{}', '{"result": "ok"}', '[]', '{"issues": "none"}'):
        folder = tmp_path / f"case{abs(hash(output))}"
        folder.mkdir()
        result = run_check(make_run(folder), scripts=make_scripts(folder, docs_output=output, docs_rc=0))
        assert result.returncode == 2, output


def test_check_run_turns_a_script_timeout_into_an_error(tmp_path):
    scripts = make_scripts(tmp_path, verify_sleep=5)
    result = run_check(make_run(tmp_path), "--timeout", "1", scripts=scripts)
    assert result.returncode == 2 and "did not finish" in result.stderr


def test_check_run_skips_check_docs_without_drafts(tmp_path):
    scripts = make_scripts(tmp_path, docs_output="not json", docs_rc=1)
    result = run_check(make_run(tmp_path, drafts=False), scripts=scripts)
    assert result.returncode == 0 and "skipped" in result.stdout
    assert not (tmp_path / "docs-argv.json").exists()


def test_check_run_takes_extra_drafts_by_glob(tmp_path):
    scripts = make_scripts(tmp_path)
    run = make_run(tmp_path, drafts=False)
    (run / "legal").mkdir()
    (run / "legal" / "privacy.html").write_text("<p>x</p>", encoding="utf-8")
    assert run_check(run, "--drafts", "legal/*.html", scripts=scripts).returncode == 0
    drafts, public = docs_call(tmp_path)
    assert [Path(p).name for p in drafts] == ["privacy.html"] and public == []


def test_check_run_reports_unreadable_check_docs_output_as_an_error(tmp_path):
    scripts = make_scripts(tmp_path, docs_output="Traceback...", docs_rc=1)
    assert run_check(make_run(tmp_path), scripts=scripts).returncode == 2


def test_check_run_errors_on_missing_report_or_answers(tmp_path):
    scripts = make_scripts(tmp_path)
    assert run_check(make_run(tmp_path, report=False), scripts=scripts).returncode == 2
    other = tmp_path / "second"
    other.mkdir()
    assert run_check(make_run(other, answers=False), scripts=scripts).returncode == 2


# --- golden reports ---------------------------------------------------------------------------

TOP_KEYS = {"version", "generated", "product", "mode", "rows", "registries", "not_checked"}
MODES = {"repo+prod", "prod-only", "repo-only"}
ROW_KEYS = {"req", "title", "status", "evidence", "norm", "level", "confidence", "effective_from", "source",
            "sources", "bucket", "element", "basis"}
STATUSES = {"present", "missing", "partial", "not_visible", "n_a"}
LEVELS = {"mandatory", "conditional", "recommended", "interpretation"}
SOURCES = {"base", "official_runtime", "market", "platform"}
BUCKETS = {"done", "owner", "disputed", "roadmap"}
BASES = {"norm", "practice", "interpretation", "inference", "platform"}
REGISTRY_STATUSES = {"ok", "not_found", "manual", "error"}
GOLDEN_DIRS = sorted(p for p in GOLDEN.iterdir() if p.is_dir())
ELEMENTS = {f"{e['template']}:{e['id']}": e for e in load_json(KB / "elements.json")}
TODAY = date.fromisoformat(GOLDEN_TODAY)


def row_violations(row, today):
    """The report.py verify rules from the Task 6 contract, applied to one row."""
    if set(row) != ROW_KEYS:
        return [f"keys differ: {sorted(set(row) ^ ROW_KEYS)}"]
    problems = []
    for key, allowed in (("status", STATUSES), ("level", LEVELS), ("source", SOURCES), ("bucket", BUCKETS),
                         ("basis", BASES), ("confidence", {"high", "medium", "low"})):
        if row[key] not in allowed:
            problems.append(f"bad {key}: {row[key]!r}")
    record = REQUIREMENTS.get(row["req"]) if row["req"] is not None else None
    if row["req"] is not None and record is None:
        problems.append(f"unknown id {row['req']}")
    if row["status"] in ("present", "missing", "partial") and not row["evidence"]:
        problems.append("this status needs evidence")
    for item in row["evidence"]:
        if not (("file" in item and isinstance(item.get("line"), int)) or "url" in item):
            problems.append(f"bad evidence {item}")
    for url in row["sources"]:
        if not host_is_official(url):
            problems.append(f"source outside the allowlist: {url}")
    if row["effective_from"] and date.fromisoformat(row["effective_from"]) > today and row["bucket"] != "roadmap":
        problems.append("future date outside the roadmap")
    if (row["source"] == "platform" or row["basis"] == "platform") and row["level"] not in ("recommended", "interpretation"):
        problems.append("platform rows are recommended or interpretation only")
    if row["level"] == "mandatory":
        if row["basis"] != "norm":
            problems.append("mandatory needs basis norm")
        if row["source"] not in ("base", "official_runtime"):
            problems.append("mandatory needs source base or official_runtime")
        if record is None:
            problems.append("mandatory needs a requirement")
        else:
            if record["source_kind"] not in ("law", "bylaw"):
                problems.append("mandatory needs a law or by-law requirement")
            if record["legal_confidence"] == "low":
                problems.append("mandatory needs confidence above low")
        element = ELEMENTS.get(row["element"]) if row["element"] is not None else None
        if row["element"] is not None and (element is None or element["status"] != "обязательно" or element["method"] != "norm"):
            problems.append("mandatory needs an «обязательно» norm element")
    if row["element"] is not None:
        element = ELEMENTS.get(row["element"])
        if element is None or row["req"] not in element["requirements"]:
            problems.append(f"element {row['element']} does not belong to {row['req']}")
    return problems


def test_golden_reports_exist_for_a_plain_case_and_a_roadmap_case():
    assert {p.name for p in GOLDEN_DIRS} == {"landing-static", "saas-nest-react"}


def test_golden_landing_has_answers_and_a_filled_draft_for_check_docs():
    golden = GOLDEN / "landing-static" / ".legal"
    answers = load_json(golden / "answers.json")
    fixture = load_json(FIXTURES / "landing-static" / ".legal" / "answers.json")
    assert answers["decisions"]["apply_changes"] is False, "the golden is an audit without edits"
    fixture["decisions"]["apply_changes"] = False
    assert answers == fixture
    drafts = sorted((golden / "drafts").glob("*.md"))
    assert drafts, "check_docs needs a draft to run on"
    owner = answers["owner"]
    for draft in drafts:
        text = draft.read_text(encoding="utf-8")
        assert "{{" not in text and "}}" not in text, "no unfilled placeholder"
        assert not re.search(r"^\[(если|Вариант)", text, re.M), "no unresolved conditional block"
        for value in (owner["name"], owner["inn"], owner["ogrn"], owner["address"], owner["email"]):
            assert value in text, value
        assert inn_valid(owner["inn"]) and ogrn_valid(owner["ogrn"])


def make_row(**changes):
    row = {"req": "ru:politika-obrabotki-pdn", "title": "t", "status": "missing",
           "evidence": [{"file": "index.html", "line": 1}], "norm": "152-ФЗ ст. 18.1 ч. 2", "level": "mandatory",
           "confidence": "high", "effective_from": "2022-09-01", "source": "base", "sources": [],
           "bucket": "owner", "element": "politika-obrabotki-pdn:А1", "basis": "norm"}
    row.update(changes)
    return row


def test_the_row_rules_accept_clean_rows_and_reject_each_violation():
    assert row_violations(make_row(), TODAY) == []
    assert row_violations(make_row(level="recommended", source="platform", basis="platform", element=None), TODAY) == []
    assert row_violations(make_row(level="conditional", effective_from="2027-03-01", bucket="roadmap",
                                   element=None), TODAY) == []
    cases = {
        "basis": make_row(basis="practice"),
        "source": make_row(source="market"),
        "requirement": make_row(req=None, element=None),
        "source kind": make_row(req="ru:sposob-vozvrata-distancionno-kuplennogo-tovara", element=None),
        "element status": make_row(element="politika-obrabotki-pdn:А2"),
        "element of another requirement": make_row(element="svedeniya-o-prodavce-i-vladelce-sayta:А1"),
        "unknown id": make_row(req="ru:nope"),
        "evidence": make_row(evidence=[]),
        "future date": make_row(level="conditional", effective_from="2027-03-01", element=None),
        "platform level": make_row(source="platform", basis="platform", element=None),
        "allowlist": make_row(sources=["https://example.com/law"]),
        "keys": {"req": None},
    }
    for name, row in cases.items():
        assert row_violations(row, TODAY), f"rule {name} did not fire"


@pytest.mark.parametrize("golden", GOLDEN_DIRS, ids=lambda p: p.name)
def test_golden_report_follows_the_canonical_shape_and_the_verify_rules(golden):
    report = load_json(golden / ".legal" / "report.json")
    sources = load_json(golden / ".legal" / "sources.json")
    assert isinstance(sources, list)
    assert set(report) - {"lang"} == TOP_KEYS, "owner data lives in answers.json, not in report.json"
    assert report["version"] == 1 and report["generated"] == GOLDEN_TODAY
    assert report.get("lang", "ru") in ("ru", "en")
    assert report["mode"] in MODES
    assert isinstance(report["product"], dict) and report["product"]["name"]
    assert isinstance(report["not_checked"], list) and report["not_checked"]
    for registry in report["registries"]:
        assert set(registry) == {"name", "status", "url", "note"}
        assert registry["status"] in REGISTRY_STATUSES
        if registry["status"] == "manual":
            assert registry["note"], "a manual check carries the step for the user"
    rows = report["rows"]
    assert len(rows) >= 8
    seen = set()
    for row in rows:
        assert row_violations(row, TODAY) == [], (row["title"], row_violations(row, TODAY))
        assert row["title"].strip() and row["norm"]
        if row["req"] is not None:
            assert row["req"] not in seen, f"{row['req']} listed twice"
            seen.add(row["req"])
            record = REQUIREMENTS[row["req"]]
            if record["effective_from"] != "mixed":
                assert row["effective_from"] == record["effective_from"]
    assert any(r["bucket"] == "disputed" for r in rows) and any(r["bucket"] == "owner" for r in rows)
    assert any(r["level"] == "mandatory" for r in rows), "the goldens exercise the mandatory path"


def test_saas_golden_puts_the_ai_norm_on_the_roadmap_with_the_card_date():
    rows = {r["req"]: r for r in load_json(GOLDEN / "saas-nest-react" / ".legal" / "report.json")["rows"]}
    row = rows["ru:obyazannosti-servisa-generativnogo-ii-243-fz"]
    assert row["bucket"] == "roadmap"
    assert row["effective_from"] == REQUIREMENTS["ru:obyazannosti-servisa-generativnogo-ii-243-fz"]["effective_from"]
    assert row["level"] != "mandatory"
    assert rows["ru:avtospisaniya-po-podpiskam"]["bucket"] != "roadmap"


@pytest.mark.parametrize("golden", GOLDEN_DIRS, ids=lambda p: p.name)
def test_golden_evidence_points_at_real_fixture_lines(golden):
    fixture = FIXTURES / golden.name
    for row in load_json(golden / ".legal" / "report.json")["rows"]:
        for item in row["evidence"]:
            if "file" not in item:
                continue
            path = fixture / item["file"]
            assert path.is_file(), f"{golden.name}: {item['file']} is not in the fixture"
            lines = path.read_text(encoding="utf-8").splitlines()
            assert 1 <= item["line"] <= len(lines), f"{item['file']}:{item['line']}"


SCRIPTS_READY = (SCRIPTS / "report.py").is_file() and (SCRIPTS / "check_docs.py").is_file()


@pytest.mark.skipif(not SCRIPTS_READY, reason="skill scripts are not written yet")
@pytest.mark.parametrize("golden", GOLDEN_DIRS, ids=lambda p: p.name)
def test_check_run_passes_on_the_golden_report(golden):
    result = subprocess.run([sys.executable, str(CHECK_RUN), str(golden), "--today", GOLDEN_TODAY],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
