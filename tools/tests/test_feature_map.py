"""Checks for the Russian requirement map (jurisdictions/ru/feature-map.json).

The map links neutral product features (features/catalog.json), owner facts
(from .legal/answers.json) and confirmed sectors to requirement ids of
requirements.jsonl. It is hand-written; tools/seed_feature_map.py only seeds a
draft. Stdlib + pytest only; paths are resolved from this file.
"""

import datetime
import importlib.util
import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RU_DIR = ROOT / "skills" / "legal-kit" / "references" / "jurisdictions" / "ru"
MAP_PATH = RU_DIR / "feature-map.json"
REQUIREMENTS_PATH = RU_DIR / "requirements.jsonl"
OWNER_QUESTIONS_PATH = RU_DIR / "owner-questions.md"
CATALOG_PATH = ROOT / "skills" / "legal-kit" / "references" / "features" / "catalog.json"
SEED_SCRIPT = ROOT / "tools" / "seed_feature_map.py"
SCRIPTS = ROOT / "skills" / "legal-kit" / "scripts"
TODAY = datetime.date(2026, 10, 18)

EXPECTED_REQUIREMENTS = 227
TOP_KEYS = {"_doc", "always", "features", "owner_facts", "sectoral", "not_detectable", "notes", "platform_rules",
            "templates", "documents"}
# Features that are evidence only and may map to no requirement (see the map's "_doc").
EVIDENCE_ONLY_PREFIXES = ("sector.",)
EVIDENCE_ONLY_IDS = ("chat.messenger_links",)
BASE_SECTORS = ("medical", "finance", "education", "gambling", "alcohol-tobacco", "gov", "taxi-tourism")
SECTOR_KEY_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
THRESHOLD_RE = re.compile(r"тыс\.|млн|>\s*\d")
# Owner facts the map may use. Each one is derived from .legal/answers.json; the
# derivation is documented in the map's "_doc".
ALLOWED_OWNER_FACTS = (
    "subject:ul", "subject:ip", "subject:npd", "subject:foreign",
    "b2c", "minors", "revenue_over_20m", "domain_ru",
)
EVIDENCE_RE = re.compile(r"^(feature|okved|licence|registry|owner_confirms|sector)(:.+)?$")
PRIVATE_PATTERNS = ("raw/articles", "raw/notes", "[[", "../topics/", "/Us" + "ers/", "llm" + "-wiki",
                    "wiki/concepts", "wiki/references")


@lru_cache(maxsize=None)
def feature_map():
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def requirements():
    records = [json.loads(line) for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines() if line]
    return {r["id"]: r for r in records}


@lru_cache(maxsize=None)
def catalog_ids():
    return frozenset(entry["id"] for entry in json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


def ids_of(obligation=None, source_kind=None):
    return {
        rid for rid, r in requirements().items()
        if (obligation is None or r["obligation"] == obligation)
        and (source_kind is None or r["source_kind"] == source_kind)
    }


def bucket_ids(fmap):
    """Requirement ids per bucket, plus the flat list of every reference."""
    buckets = {
        "always": list(fmap["always"]),
        "features": [i for ids in fmap["features"].values() for i in ids],
        "owner_facts": [i for ids in fmap["owner_facts"].values() for i in ids],
        "sectoral": [i for group in fmap["sectoral"].values() for i in group["requirements"]],
        "not_detectable": list(fmap["not_detectable"]),
    }
    return buckets


def all_lists(fmap):
    yield "always", fmap["always"]
    yield "platform_rules", fmap["platform_rules"]
    for section in ("templates", "documents"):
        for name, rule in fmap.get(section, {}).items():
            yield "%s.%s.features" % (section, name), rule["features"]
            yield "%s.%s.facts" % (section, name), rule["facts"]
    for key, ids in fmap["features"].items():
        yield "features." + key, ids
    for key, ids in fmap["owner_facts"].items():
        yield "owner_facts." + key, ids
    for key, group in fmap["sectoral"].items():
        yield "sectoral.%s.requirements" % key, group["requirements"]
        yield "sectoral.%s.evidence" % key, group["evidence"]


def load_script(name):
    """Import a skill script by path under a unique module name (select.py shadows a stdlib module)."""
    module_name = name if name == "_kb" else "legalkit_" + name
    if module_name in sys.modules:
        return sys.modules[module_name]
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def make_inputs(features=(), subject=None, models=(), products=(), sectors=(), facts=(), planned=()):
    facts = set(facts)
    if subject:
        facts.add("subject:" + subject)
    if "b2c" in models:
        facts.add("b2c")
    return {"features": list(features), "planned": list(planned), "subject": subject, "models": sorted(models),
            "products": sorted(products), "sectors": sorted(sectors), "facts": sorted(facts)}


def union(fmap, features=(), facts=(), sectors=()):
    """Candidate ids as scripts/select.py builds them (before the subject/model/product filter)."""
    inputs = make_inputs(features=features, sectors=sectors, facts=facts)
    return set(load_script("select").candidates(fmap, inputs, []))


def run_select(**kwargs):
    return load_script("select").select(RU_DIR, make_inputs(**kwargs), TODAY)


# --------------------------------------------------------------------------
# shape
# --------------------------------------------------------------------------

def test_requirements_count_matches_brief():
    assert len(requirements()) == EXPECTED_REQUIREMENTS


def test_map_is_valid_json_with_expected_keys():
    fmap = feature_map()
    assert set(fmap) == TOP_KEYS
    assert isinstance(fmap["_doc"], str) and fmap["_doc"].strip()
    assert isinstance(fmap["always"], list)
    assert isinstance(fmap["features"], dict)
    assert isinstance(fmap["owner_facts"], dict)
    assert isinstance(fmap["sectoral"], dict)
    assert isinstance(fmap["not_detectable"], dict)
    assert isinstance(fmap["platform_rules"], list)


def test_lists_are_sorted_without_duplicates():
    for name, values in all_lists(feature_map()):
        assert all(isinstance(v, str) and v for v in values), name
        assert values == sorted(set(values)), "%s must be sorted and unique" % name


def test_no_private_patterns_in_map_and_seed_script():
    for path in (MAP_PATH, SEED_SCRIPT):
        text = path.read_text(encoding="utf-8")
        hits = [p for p in PRIVATE_PATTERNS if p in text]
        assert not hits, "%s: %s" % (path.name, hits)


# --------------------------------------------------------------------------
# coverage and references
# --------------------------------------------------------------------------

def test_every_requirement_is_covered():
    covered = set().union(*map(set, bucket_ids(feature_map()).values()))
    missing = sorted(set(requirements()) - covered)
    assert not missing, "not mapped anywhere: %s" % missing


def test_no_unknown_requirement_ids():
    known = set(requirements())
    unknown = []
    for name, values in all_lists(feature_map()):
        if name.endswith(".evidence") or name.startswith(("templates.", "documents.")):
            continue
        unknown += ["%s: %s" % (name, v) for v in values if v not in known]
    unknown += ["not_detectable: %s" % v for v in feature_map()["not_detectable"] if v not in known]
    assert not unknown, unknown


def evidence_only(feature):
    return feature.startswith(EVIDENCE_ONLY_PREFIXES) or feature in EVIDENCE_ONLY_IDS


def test_feature_keys_are_catalog_ids_with_requirements():
    for feature, ids in feature_map()["features"].items():
        assert feature in catalog_ids(), "unknown feature %s" % feature
        assert ids or evidence_only(feature), "feature %s maps to no requirement" % feature


def test_every_catalog_feature_is_in_the_map():
    missing = sorted(catalog_ids() - set(feature_map()["features"]))
    assert not missing, "catalog features absent from the map (select.py would warn): %s" % missing


def test_evidence_only_features_are_documented():
    assert "evidence only" in feature_map()["_doc"]
    for feature in EVIDENCE_ONLY_IDS:
        assert feature in feature_map()["_doc"]


def test_owner_fact_keys_are_allowed_and_documented():
    fmap = feature_map()
    for fact, ids in fmap["owner_facts"].items():
        assert fact in ALLOWED_OWNER_FACTS, "owner fact %s is not allowed" % fact
        assert ids, "owner fact %s maps to no requirement" % fact
    for fact in ALLOWED_OWNER_FACTS:
        assert fact in fmap["_doc"], "_doc does not document owner fact %s" % fact


def test_not_detectable_reasons_are_non_empty():
    for rid, reason in feature_map()["not_detectable"].items():
        assert isinstance(reason, str) and len(reason.strip()) >= 20, rid


def test_notes_name_known_mapped_ids():
    fmap = feature_map()
    mapped = set().union(*map(set, bucket_ids(fmap).values()))
    for rid, note in fmap["notes"].items():
        assert rid in requirements(), "note for unknown id %s" % rid
        assert rid in mapped, "note for an id that is not mapped: %s" % rid
        assert isinstance(note, str) and len(note.strip()) >= 15, rid


def test_licence_specific_sector_ids_carry_a_sub_status_note():
    notes = feature_map()["notes"]
    for rid in ("ru:ib-bankovskih-prilozheniy-851-p", "ru:ib-prilozheniy-nfo-757-p", "ru:mikrofinansovye-organizacii-onlayn",
                "ru:potrebitelskiy-kredit-onlayn", "ru:operator-finansovoy-platformy-211-fz",
                "ru:postavshchik-platezhnogo-prilozheniya", "ru:servis-rassrochki-operator", "ru:distancionnaya-prodazha-lekarstv",
                "ru:sluzhba-zakaza-legkovogo-taksi", "ru:sayt-turoperatora-i-turagenta", "ru:gossopka-dlya-operatorov-gis",
                "ru:zashchita-informacii-v-gis"):
        assert rid in notes, "no sub-status note for %s" % rid


def test_always_ids_fit_both_models():
    for rid in feature_map()["always"]:
        assert {"b2b", "b2c"} <= set(requirements()[rid]["models"]), "%s in always is not for both b2b and b2c" % rid


def test_threshold_triggers_only_in_sectoral_or_not_detectable():
    fmap = feature_map()
    allowed = set(bucket_ids(fmap)["sectoral"]) | set(fmap["not_detectable"]) | set(fmap["owner_facts"].get("revenue_over_20m", []))
    elsewhere = set(fmap["always"]) | set(bucket_ids(fmap)["features"]) | {
        i for k, ids in fmap["owner_facts"].items() if k != "revenue_over_20m" for i in ids}
    for rid, record in requirements().items():
        if THRESHOLD_RE.search(record["trigger"]):
            assert rid in allowed, "threshold trigger %s is not in sectoral/not_detectable" % rid
            assert rid not in elsewhere, "threshold trigger %s is mapped to a feature, always or a fact" % rid


# --------------------------------------------------------------------------
# sectoral and platform rules
# --------------------------------------------------------------------------

def test_sectoral_requirements_only_in_sectoral():
    buckets = bucket_ids(feature_map())
    sectoral = ids_of(obligation="sectoral")
    for name in ("always", "features", "owner_facts", "not_detectable"):
        leaked = sorted(sectoral & set(buckets[name]))
        assert not leaked, "sectoral requirements in %s: %s" % (name, leaked)
    assert sectoral <= set(buckets["sectoral"])


def test_every_sectoral_group_has_evidence_and_requirements():
    for name, group in feature_map()["sectoral"].items():
        assert set(group) == {"evidence", "requirements"}, name
        assert group["requirements"], "group %s has no requirements" % name
        assert group["evidence"], "group %s has no evidence" % name
        for item in group["evidence"]:
            assert EVIDENCE_RE.match(item), "%s: bad evidence %r" % (name, item)
            if item.startswith("feature:"):
                assert item[len("feature:"):] in catalog_ids(), "%s: %s" % (name, item)
            if item.startswith("sector:"):
                assert item[len("sector:"):] in feature_map()["sectoral"], "%s: %s" % (name, item)
        assert any(e.startswith("owner_confirms") for e in group["evidence"]), \
            "group %s must require owner confirmation" % name


def test_answers_sectors_are_the_sectoral_keys():
    text = OWNER_QUESTIONS_PATH.read_text(encoding="utf-8")
    match = re.search(r'"sectors":\s*"([^"]+)"', text)
    assert match, "business.sectors not found in owner-questions.md"
    schema = match.group(1)
    assert "sectoral" in schema and "feature-map.json" in schema, "business.sectors must refer to feature-map sectoral keys"
    groups = feature_map()["sectoral"]
    for sector in BASE_SECTORS:
        assert sector in groups, "no sectoral group for base sector %s" % sector
        assert "`%s`" % sector in text, "owner-questions.md does not name sector %s" % sector
    for key in groups:
        assert SECTOR_KEY_RE.match(key), "sectoral key %r is not a valid business.sectors value" % key


def test_platform_rules_are_exactly_store_policy_ids():
    store = ids_of(source_kind="store-policy")
    assert store, "no store-policy requirements found"
    assert set(feature_map()["platform_rules"]) == store


# --------------------------------------------------------------------------
# behaviour
# --------------------------------------------------------------------------

def test_contact_form_and_counter_for_b2c_company():
    ids = union(feature_map(), features=("forms.contact", "analytics.web_counter"), facts=("subject:ul", "b2c"))
    assert "ru:politika-obrabotki-pdn" in ids
    assert "ru:soglasie-na-analitiku-i-cookies" in ids
    assert not ids & ids_of(obligation="sectoral")
    assert not ids & set(feature_map()["platform_rules"]), "store rules need a mobile feature"


def test_sector_requirements_need_a_confirmed_sector():
    fmap = feature_map()
    every_feature = tuple(fmap["features"])
    every_fact = tuple(fmap["owner_facts"])
    without = union(fmap, features=every_feature, facts=every_fact)
    assert not without & ids_of(obligation="sectoral")
    with_medical = union(fmap, sectors=("medical",))
    assert "ru:sayt-medicinskoy-organizacii" in with_medical


def test_always_holds_only_general_or_conditional_requirements():
    for rid in feature_map()["always"]:
        assert requirements()[rid]["obligation"] in ("general", "conditional"), rid


# --------------------------------------------------------------------------
# templates and documents (consumed by select.py)
# --------------------------------------------------------------------------

def template_names():
    return {p.name for p in (RU_DIR / "templates").iterdir() if p.is_dir()}


def document_names():
    return {p.stem for p in (RU_DIR / "documents").glob("*.md")}


@pytest.mark.parametrize("section,names", [("templates", template_names), ("documents", document_names)])
def test_every_template_and_document_has_a_rule(section, names):
    rules = feature_map()[section]
    assert set(rules) == names(), "%s keys differ from the files: %s" % (section, sorted(set(rules) ^ names()))
    allowed_facts = set(ALLOWED_OWNER_FACTS) | set(feature_map()["sectoral"]) | {
        "sector:" + k for k in feature_map()["sectoral"]}
    for name, rule in rules.items():
        assert set(rule) == {"features", "facts", "always"}, name
        assert isinstance(rule["always"], bool), name
        assert rule["always"] or rule["features"] or rule["facts"], "%s.%s is never selected" % (section, name)
        assert set(rule["features"]) <= catalog_ids(), "%s.%s: unknown features %s" % (
            section, name, sorted(set(rule["features"]) - catalog_ids()))
        assert set(rule["facts"]) <= allowed_facts, "%s.%s: unknown facts" % (section, name)


def test_counts_of_templates_and_documents():
    assert len(feature_map()["templates"]) == 9
    assert len(feature_map()["documents"]) == 13


# --------------------------------------------------------------------------
# goldens: six typical products (feature sets as scan_repo.py finds them in evals/fixtures)
# --------------------------------------------------------------------------

def rid(*slugs):
    return {"ru:" + s for s in slugs}


GOLDENS = {
    "landing": dict(
        inputs=dict(features=("forms.contact", "analytics.web_counter", "analytics.session_replay", "auth.telegram"),
                    subject="ul", models=("b2c",), products=("site",)),
        include=rid("politika-obrabotki-pdn", "soglasie-na-obrabotku-pdn", "soglasie-na-analitiku-i-cookies",
                    "cookies-i-identifikatory-kak-pdn", "svedeniya-o-vladelce-sayta", "uvedomlenie-rkn-ob-obrabotke-pdn",
                    "lokalizaciya-pdn", "sposoby-avtorizacii-polzovateley"),
        exclude=rid("transgranichnaya-peredacha-pdn", "publichnaya-oferta-i-podtverzhdenie-zakaza",
                    "onlayn-kkt-i-elektronnyy-chek", "srok-peredachi-predoplachennogo-tovara"),
        templates=({"politika-obrabotki-pdn", "soglasie-na-obrabotku-pdn", "cookie-banner-i-uvedomlenie"},
                   {"publichnaya-oferta-tovary", "oferta-uslugi-i-podpiska"}),
        documents=({"rkn-notification"}, {"kkt-checklist", "gift-cards", "cross-border-notification"})),
    "landing-jquery-cdn": dict(
        inputs=dict(features=("forms.contact", "foreign.static_cdn"), subject="ul", models=("b2c",), products=("site",)),
        include=rid("postavshchiki-analitiki-i-sdk", "posledstviya-mer-236-fz-dlya-rossiyskih-vladelcev"),
        exclude=rid("transgranichnaya-peredacha-pdn", "poruchenie-obrabotki-pdn"),
        templates=(set(), {"cookie-banner-i-uvedomlenie"}),
        documents=(set(), {"cross-border-notification", "poruchenie"})),
    "store": dict(
        inputs=dict(features=("analytics.web_counter", "commerce.cart_physical", "commerce.checkout", "forms.contact",
                              "payments.receipts_kkt", "payments.yookassa"),
                    subject="ul", models=("b2c",), products=("site",)),
        include=rid("publichnaya-oferta-i-podtverzhdenie-zakaza", "vozvrat-tovara-pri-distancionnoy-prodazhe",
                    "informaciya-o-tovare-pri-distancionnoy-prodazhe", "svedeniya-o-prodavce-pri-distancionnoy-prodazhe",
                    "onlayn-kkt-i-elektronnyy-chek", "cena-v-rublyah-i-polnaya-summa",
                    "srok-peredachi-predoplachennogo-tovara", "edinaya-cena-nezavisimo-ot-sposoba-oplaty",
                    "akcept-polzovatelskogo-soglasheniya", "nedopustimye-usloviya-oferty",
                    "russkiy-yazyk-informacii-dlya-potrebiteley", "sposob-vozvrata-distancionno-kuplennogo-tovara"),
        exclude=rid("avtospisaniya-po-podpiskam", "dogovor-uslug-informaciya-sroki-nedostatki",
                    "transgranichnaya-peredacha-pdn"),
        templates=({"publichnaya-oferta-tovary", "usloviya-vozvrata-i-obmena", "svedeniya-o-prodavce-i-vladelce-sayta"},
                   {"oferta-uslugi-i-podpiska"}),
        documents=({"kkt-checklist"}, {"gift-cards", "promo-rules"})),
    "saas": dict(
        inputs=dict(features=("analytics.session_replay", "analytics.web_counter", "commerce.subscription",
                              "commerce.trial", "forms.registration", "payments.cloudpayments", "tech.generative_ai"),
                    subject="ul", models=("b2c",), products=("site", "webapp")),
        include=rid("avtospisaniya-po-podpiskam", "otkaz-ot-uslug-i-cifrovyh-podpisok", "akcept-polzovatelskogo-soglasheniya",
                    "sposoby-avtorizacii-polzovateley", "onlayn-kkt-i-elektronnyy-chek", "poruchenie-obrabotki-pdn",
                    "licenzionnoe-soglashenie-s-polzovatelem-eula", "obyazannosti-servisa-generativnogo-ii-243-fz"),
        exclude=rid("srok-peredachi-predoplachennogo-tovara", "vozvrat-tovara-pri-distancionnoy-prodazhe",
                    "nedostatki-i-garantiya-tovara", "obyazatelnoe-primenenie-suverennyh-modeley-ii",
                    "publichnaya-oferta-i-podtverzhdenie-zakaza"),
        templates=({"oferta-uslugi-i-podpiska"}, {"publichnaya-oferta-tovary", "usloviya-vozvrata-i-obmena"}),
        documents=({"kkt-checklist", "poruchenie", "user-agreement"}, {"gift-cards"})),
    "mobile": dict(
        inputs=dict(features=("analytics.mobile_sdk", "comms.push", "forms.registration", "mobile.app", "mobile.iap"),
                    subject="ul", models=("b2c",), products=("ios", "android")),
        include=rid("pravila-storov-trekking-i-raskrytie-dannyh", "pravila-storov-oplata-i-podpiski",
                    "pravila-storov-push-i-marketing", "pravila-storov-akkaunty-i-vhod", "reklamnye-push-uvedomleniya",
                    "cifrovoy-kontent-i-prava-potrebitelya", "svedeniya-o-prodavce-pri-distancionnoy-prodazhe",
                    "cheki-pri-prodazhe-cherez-agentov-i-story"),
        exclude=rid("transgranichnaya-peredacha-pdn", "edinyy-magazin-prilozheniy", "svedeniya-o-vladelce-sayta"),
        templates=({"soglasie-na-rassylku", "cookie-banner-i-uvedomlenie", "oferta-uslugi-i-podpiska"}, set()),
        documents=({"user-agreement"}, {"cross-border-notification"})),
    "mobile-firebase-rustore": dict(
        inputs=dict(features=("analytics.mobile_sdk", "comms.push", "forms.registration", "mobile.app", "mobile.iap",
                              "foreign.data_processors", "mobile.rustore"),
                    subject="ul", models=("b2c",), products=("ios", "android")),
        include=rid("transgranichnaya-peredacha-pdn", "poruchenie-obrabotki-pdn", "edinyy-magazin-prilozheniy"),
        exclude=set(),
        templates=(set(), set()),
        documents=({"cross-border-notification", "poruchenie"}, set())),
    "courses": dict(
        inputs=dict(features=("analytics.web_counter", "commerce.checkout", "content.webinars", "forms.generic",
                              "payments.receipts_kkt", "payments.yookassa", "sector.education_courses"),
                    subject="ul", models=("b2c",), products=("site",)),
        include=rid("dogovor-uslug-informaciya-sroki-nedostatki", "otkaz-ot-uslug-i-cifrovyh-podpisok",
                    "onlayn-obuchenie-licenziya-i-prosveshchenie", "onlayn-kkt-i-elektronnyy-chek",
                    "cena-v-rublyah-i-polnaya-summa", "svedeniya-o-prodavce-pri-distancionnoy-prodazhe",
                    "izobrazhenie-grazhdanina-v-kontente"),
        exclude=rid("srok-peredachi-predoplachennogo-tovara", "vozvrat-tovara-pri-distancionnoy-prodazhe",
                    "publichnaya-oferta-i-podtverzhdenie-zakaza", "sayt-obrazovatelnoy-organizacii",
                    "dokumenty-ob-obuchenii-po-itogam-kursa"),
        templates=({"oferta-uslugi-i-podpiska", "soglasie-na-obrabotku-pdn"}, {"publichnaya-oferta-tovary"}),
        documents=({"image-consent", "kkt-checklist"}, set())),
    "courses-education-confirmed": dict(
        inputs=dict(features=("sector.education_courses", "commerce.checkout"), subject="ul", models=("b2c",),
                    products=("site",), sectors=("education",)),
        include=rid("dokumenty-ob-obuchenii-po-itogam-kursa", "elektronnoe-obuchenie-i-dot", "sayt-obrazovatelnoy-organizacii"),
        exclude=set(),
        templates=(set(), set()),
        documents=(set(), set())),
    "services": dict(
        inputs=dict(features=("analytics.mobile_sdk", "commerce.prepayment", "commerce.services_booking",
                              "foreign.cdn_hosting", "foreign.data_processors", "mobile.app", "payments.yookassa",
                              "ugc.image_uploads", "ugc.reviews", "ugc.uploads"),
                    subject="ip", models=("b2c",), products=("ios", "android")),
        include=rid("dogovor-uslug-informaciya-sroki-nedostatki", "soglasie-na-rasprostranenie-pdn",
                    "izobrazhenie-grazhdanina-v-kontente", "otzyvy-reytingi-i-beydzhi", "transgranichnaya-peredacha-pdn",
                    "onlayn-kkt-i-elektronnyy-chek", "pravila-storov-polzovatelskiy-kontent"),
        exclude=rid("srok-peredachi-predoplachennogo-tovara", "vozvrat-tovara-pri-distancionnoy-prodazhe",
                    "publichnaya-oferta-i-podtverzhdenie-zakaza", "edinyy-magazin-prilozheniy"),
        templates=({"oferta-uslugi-i-podpiska", "soglasie-na-rasprostranenie-pdn"},
                   {"publichnaya-oferta-tovary", "usloviya-vozvrata-i-obmena"}),
        documents=({"image-consent", "cross-border-notification"}, set())),
    "bot-shop": dict(
        inputs=dict(features=("bot.telegram", "payments.bot_invoice", "payments.telegram_stars"),
                    subject="ul", models=("b2c",), products=("bot",)),
        include=rid("dokumenty-i-soglasiya-v-chat-bote", "oplata-v-chat-bote-i-chek",
                    "pdn-pri-sbore-cherez-inostrannyy-messendzher", "onlayn-kkt-i-elektronnyy-chek",
                    "zapret-oplaty-cifrovoy-valyutoy", "pravila-platform-botov-oplata", "soglasie-na-obrabotku-pdn"),
        exclude=rid("pravila-storov-oplata-i-podpiski", "soglasie-na-analitiku-i-cookies"),
        templates=({"soglasie-na-obrabotku-pdn", "politika-obrabotki-pdn"}, {"cookie-banner-i-uvedomlenie"}),
        documents=({"kkt-checklist"}, set())),
}


@pytest.mark.parametrize("name", sorted(GOLDENS))
def test_golden_requirements(name):
    golden = GOLDENS[name]
    out = run_select(**golden["inputs"])
    applicable = {item["id"] for item in out["applicable"]}
    missing = sorted(golden["include"] - applicable)
    assert not missing, "%s: must include %s" % (name, missing)
    extra = sorted(golden["exclude"] & applicable)
    assert not extra, "%s: must exclude %s" % (name, extra)
    if not golden["inputs"].get("sectors"):
        assert not applicable & ids_of(obligation="sectoral"), name
    platform = set(feature_map()["platform_rules"])
    store_rules = {i for i in platform if i.startswith("ru:pravila-storov-")}
    bot_rules = platform - store_rules
    if not set(golden["inputs"]["products"]) & {"ios", "android"}:
        assert not applicable & store_rules, name
    if "bot" not in golden["inputs"]["products"]:
        assert not applicable & bot_rules, name


@pytest.mark.parametrize("name", sorted(GOLDENS))
def test_golden_templates_and_documents(name):
    golden = GOLDENS[name]
    out = run_select(**golden["inputs"])
    templates = set(out["templates"])
    documents = {d["name"] for d in out["documents"]}
    must, must_not = golden["templates"]
    assert must <= templates, "%s: templates missing %s" % (name, sorted(must - templates))
    assert not must_not & templates, "%s: templates not expected %s" % (name, sorted(must_not & templates))
    must, must_not = golden["documents"]
    assert must <= documents, "%s: documents missing %s" % (name, sorted(must - documents))
    assert not must_not & documents, "%s: documents not expected %s" % (name, sorted(must_not & documents))


# --------------------------------------------------------------------------
# goldens from real scans of the eval fixtures (scan_repo.py + the fixture's answers.json)
# --------------------------------------------------------------------------

FIXTURES_DIR = ROOT / "evals" / "fixtures"
MEDICAL_SECTOR_IDS = rid("platnye-medicinskie-uslugi-onlayn", "telemedicina-usloviya-okazaniya",
                         "telemedicina-informaciya-dlya-pacienta", "sayt-medicinskoy-organizacii",
                         "vrachebnaya-tayna-v-medicinskih-servisah")
REAL_GOLDENS = {
    # evals.json eval 3: Next.js shop of household textiles
    "store-nextjs": dict(
        include=rid("publichnaya-oferta-i-podtverzhdenie-zakaza", "vozvrat-tovara-pri-distancionnoy-prodazhe",
                    "sposob-vozvrata-distancionno-kuplennogo-tovara", "svedeniya-o-prodavce-pri-distancionnoy-prodazhe",
                    "onlayn-kkt-i-elektronnyy-chek", "nedopustimye-usloviya-oferty",
                    "russkiy-yazyk-informacii-dlya-potrebiteley", "soglasie-na-analitiku-i-cookies"),
        exclude=rid("prinyatie-nacionalnyh-platezhnyh-instrumentov", "oplata-cifrovymi-rublyami"),
        templates=({"publichnaya-oferta-tovary", "usloviya-vozvrata-i-obmena", "svedeniya-o-prodavce-i-vladelce-sayta",
                    "politika-obrabotki-pdn", "soglasie-na-obrabotku-pdn", "cookie-banner-i-uvedomlenie"},
                   {"oferta-uslugi-i-podpiska"})),
    # eval 6: online school on Django, sector education confirmed in answers.json
    "courses-django": dict(
        include=rid("soglasie-na-obrabotku-pdn", "politika-obrabotki-pdn", "otkaz-ot-uslug-i-cifrovyh-podpisok",
                    "onlayn-obuchenie-licenziya-i-prosveshchenie", "dokumenty-ob-obuchenii-po-itogam-kursa",
                    "dogovor-uslug-informaciya-sroki-nedostatki", "soglasie-na-analitiku-i-cookies"),
        exclude=rid("vozvrat-tovara-pri-distancionnoy-prodazhe", "publichnaya-oferta-i-podtverzhdenie-zakaza")
        | MEDICAL_SECTOR_IDS,
        templates=({"oferta-uslugi-i-podpiska", "politika-obrabotki-pdn", "soglasie-na-obrabotku-pdn"},
                   {"publichnaya-oferta-tovary", "usloviya-vozvrata-i-obmena"})),
    # eval 8: iOS shop with goods, a paid club subscription and paid design consultations
    "shop-swift": dict(
        include=rid("politika-obrabotki-pdn", "soglasie-na-obrabotku-pdn", "publichnaya-oferta-i-podtverzhdenie-zakaza",
                    "vozvrat-tovara-pri-distancionnoy-prodazhe", "svedeniya-o-prodavce-pri-distancionnoy-prodazhe",
                    "dogovor-uslug-informaciya-sroki-nedostatki", "otkaz-ot-uslug-i-cifrovyh-podpisok",
                    "pravila-storov-oplata-i-podpiski", "pravila-storov-trekking-i-raskrytie-dannyh",
                    "soglasie-na-analitiku-i-cookies", "transgranichnaya-peredacha-pdn"),
        exclude=MEDICAL_SECTOR_IDS | rid("svedeniya-o-vladelce-sayta"),
        templates=({"politika-obrabotki-pdn", "soglasie-na-obrabotku-pdn", "publichnaya-oferta-tovary",
                    "oferta-uslugi-i-podpiska", "cookie-banner-i-uvedomlenie"}, set())),
}


def real_scan_inputs(name):
    root = FIXTURES_DIR / name
    if not root.is_dir():
        pytest.skip("fixture %s not present" % name)
    scanned = load_script("scan_repo").scan(str(root), str(CATALOG_PATH))
    answers = json.loads((root / ".legal" / "answers.json").read_text(encoding="utf-8"))
    audience, business = answers.get("audience") or {}, answers.get("business") or {}
    facts = set()
    if audience.get("minors") in ("14-18", "under-14"):
        facts.add("minors")
    if business.get("revenue_over_20m") is True:
        facts.add("revenue_over_20m")
    return dict(features=tuple(sorted(f["id"] for f in scanned["features"])),
                subject=(answers.get("owner") or {}).get("status"),
                models=tuple(m for m in ("b2b", "b2c") if audience.get(m) is True),
                products=tuple((answers.get("product") or {}).get("kinds") or ()),
                sectors=tuple(business.get("sectors") or ()), facts=tuple(sorted(facts)))


@pytest.mark.parametrize("name", sorted(REAL_GOLDENS))
def test_real_scan_golden(name):
    golden = REAL_GOLDENS[name]
    inputs = real_scan_inputs(name)
    out = run_select(**inputs)
    applicable = {item["id"] for item in out["applicable"]}
    assert not sorted(golden["include"] - applicable), "%s (features %s): must include %s" % (
        name, inputs["features"], sorted(golden["include"] - applicable))
    assert not sorted(golden["exclude"] & applicable), "%s: must exclude %s" % (name, sorted(golden["exclude"] & applicable))
    confirmed = {i for s in inputs["sectors"] for i in feature_map()["sectoral"][s]["requirements"]}
    assert not (applicable & ids_of(obligation="sectoral")) - confirmed, "%s: unconfirmed sector ids" % name
    must, must_not = golden["templates"]
    templates = set(out["templates"])
    assert must <= templates, "%s: templates missing %s" % (name, sorted(must - templates))
    assert not must_not & templates, "%s: templates not expected %s" % (name, sorted(must_not & templates))


# --------------------------------------------------------------------------
# seed script
# --------------------------------------------------------------------------

def run_seed(*args):
    return subprocess.run([sys.executable, str(SEED_SCRIPT), *map(str, args)],
                          capture_output=True, text=True, timeout=60)


def test_seed_draft_has_map_shape_and_covers_everything(tmp_path):
    out = tmp_path / "draft.json"
    result = run_seed("--out", out)
    assert result.returncode == 0, result.stderr
    draft = json.loads(out.read_text(encoding="utf-8"))
    assert set(draft) == TOP_KEYS
    assert set(draft["features"]) <= catalog_ids()
    assert set(draft["owner_facts"]) <= set(ALLOWED_OWNER_FACTS)
    covered = set().union(*map(set, bucket_ids(draft).values()))
    assert covered == set(requirements())
    assert set(draft["platform_rules"]) == ids_of(source_kind="store-policy")
    sectoral = ids_of(obligation="sectoral")
    assert sectoral <= {i for g in draft["sectoral"].values() for i in g["requirements"]}
    assert not sectoral & {i for ids in draft["features"].values() for i in ids}


def test_seed_is_deterministic(tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    assert run_seed("--out", first).returncode == 0
    assert run_seed("--out", second).returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_seed_refuses_to_overwrite_curated_map():
    result = run_seed("--out", MAP_PATH)
    assert result.returncode == 2
    assert "curated" in result.stderr


def test_seed_takes_short_triggers_from_the_build_refs_module(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    record = {"id": "ru:demo-form", "title": "Demo", "summary": "Demo", "trigger": "", "obligation": "general",
              "source_kind": "law", "subjects": [], "models": []}
    (kb / "requirements.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    refs = tmp_path / "build_refs.py"
    refs.write_text('DIRS = {}\nTRIGGER = {"demo-form": "форма заявки на сайте"}\n', encoding="utf-8")
    plain, with_refs = tmp_path / "plain.json", tmp_path / "with-refs.json"
    assert run_seed("--kb", kb, "--out", plain).returncode == 0
    assert run_seed("--kb", kb, "--build-refs", refs, "--out", with_refs).returncode == 0
    assert "ru:demo-form" not in json.loads(plain.read_text(encoding="utf-8"))["features"].get("forms.contact", [])
    assert "ru:demo-form" in json.loads(with_refs.read_text(encoding="utf-8"))["features"]["forms.contact"]
    missing = run_seed("--kb", kb, "--build-refs", tmp_path / "nope.py", "--out", tmp_path / "x.json")
    assert missing.returncode == 2 and "build_refs.py not found" in missing.stderr


@pytest.mark.parametrize("missing", ["--kb", "--catalog"])
def test_seed_bad_input_exits_2(tmp_path, missing):
    result = run_seed(missing, tmp_path / "nope", "--out", tmp_path / "x.json")
    assert result.returncode == 2
