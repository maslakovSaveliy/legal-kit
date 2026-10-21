#!/usr/bin/env python3
"""Seed a draft of a jurisdiction's feature-map.json from the requirement records.

    seed_feature_map.py --out draft.json [--kb <pack>] [--catalog <catalog.json>] [--build-refs <build_refs.py>]

The draft links requirements to catalog features, owner facts and sector groups by
keyword rules over the short trigger, the title and the summary of each record, and by
the record fields (obligation, source_kind, subjects, models). It is a starting point
for a human: the curated feature-map.json is written by hand, so the script refuses to
overwrite it. With --build-refs the short triggers are read from the source base's table
module (only at build time; nothing from it is copied); otherwise the "trigger" field of
requirements.jsonl is used. Output is deterministic. Exit code 2: bad input. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

DEFAULT_KB = ROOT / "skills" / "legal-kit" / "references" / "jurisdictions" / "ru"
DEFAULT_CATALOG = ROOT / "skills" / "legal-kit" / "references" / "features" / "catalog.json"
CURATED_NAME = "feature-map.json"

# Feature rules: catalog id -> pattern over "trigger | title | summary" (lower case).
FEATURE_RULES = {
    "forms.contact": r"форм\w* (?:заявк|обратн)|согласи\w* на обработку",
    "forms.registration": r"регистрац\w* (?:пользоват|в продукт)|аккаунт|пользовательск\w+ соглашени|доступ после входа",
    "auth.vk_id": r"способ\w* (?:входа|авторизац)|доступ после входа",
    "auth.yandex_id": r"способ\w* (?:входа|авторизац)|доступ после входа",
    "auth.gosuslugi": r"есиа|из гис",
    "auth.google": r"способ\w* (?:входа|авторизац)|доступ после входа",
    "auth.apple": r"способ\w* (?:входа|авторизац)|доступ после входа",
    "auth.sms_otp": r"sms|смс",
    "commerce.cart_physical": r"дистанционн\w+ продаж|заказ через сайт|возврат товар|продаж\w+ потребител",
    "commerce.marked_goods": r"маркир\w+ товар|кода? маркировки",
    "commerce.digital_content": r"цифров\w+ контент|скачиваем|ключ\w* активац",
    "commerce.services_booking": r"услуг\w* потребител|запись на услуг|сайт услуг",
    "commerce.prepayment": r"предоплат|оплата при заказе",
    "commerce.subscription": r"подписк",
    "commerce.trial": r"пробн\w+ период",
    "commerce.promo_codes": r"промокод",
    "commerce.loyalty_points": r"лояльност|бонус\w* балл",
    "commerce.gift_cards": r"подарочн\w+ сертификат",
    "payments.receipts_kkt": r"\bккт\b|кассов\w+ чек|электронн\w+ чек",
    "platform.marketplace": r"маркетплейс|агрегатор\w* (?:товар|информац)|посредническ\w+ платформ|цифров\w+ платформ",
    "analytics.web_counter": r"счётчик|аналитик\w+ с пдн|cookie",
    "analytics.session_replay": r"вебвизор|запись сесси",
    "ads.pixels": r"пиксел|ретаргет",
    "analytics.tag_manager": r"менеджер\w* тегов",
    "analytics.mobile_sdk": r"\bsdk\b",
    "chat.widget": r"чат-?виджет",
    "comms.email_marketing": r"e-?mail|маркетингов\w+ контакт|рассылк",
    "comms.push": r"\bpush\b",
    "comms.sms": r"sms|смс",
    "comms.calls_calltracking": r"звонк|обзвон",
    "ugc.reviews": r"отзыв",
    "ugc.user_messaging": r"обмен\w* сообщени\w* между пользовател|мессенджер",
    "ugc.public_profiles": r"публичн\w+ профил|персональн\w+ страниц|профили",
    "ugc.uploads": r"пользовател\w+ размещают|ugc|фото и видео",
    "content.webinars": r"вебинар",
    "audience.kids": r"младше 18|несовершеннолет|дет",
    "audience.adult_18": r"18\+",
    "tech.generative_ai": r"искусственн\w+ интеллект|\bии\b|генеративн",
    "mobile.app": r"приложени\w+ в (?:стор|сторе|едином магазине)|app store|google play",
    "mobile.iap": r"платн\w+ функци\w+ в приложени|покупк\w+ в приложени",
    "mobile.att": r"\batt\b|идентификатор\w* реклам",
    "foreign.fonts": r"шрифт",
    "foreign.captcha": r"капч",
    "foreign.cdn_hosting": r"трансграничн|иностранн\w+ получател|хостинг",
    "foreign.embeds": r"встраиваем|iframe",
    "ads.own_site_promo": r"реклам\w+ в интернете|промо-блок|рекламн\w+ мест",
    "content.meta_symbols": r"instagram|facebook|meta\b",
    "content.vpn_mentions": r"\bvpn\b|обход\w* блокиров",
    "i18n.foreign_language_ui": r"русск\w+ язык|иностранн\w+ слов",
}

# Sector rules for sectoral-obligation records, checked in this order.
SECTOR_RULES = (
    ("medical", r"мед|врач|телемед|лекарств|аптек|пациент"),
    ("gambling", r"азарт|букмекер|лотере|ставк"),
    ("alcohol-tobacco", r"алкогол|табак|никотин"),
    ("education", r"образоват|обучени"),
    ("taxi-tourism", r"такси|туропер|турагент|туризм|гостиниц"),
    ("kii", r"\bкии\b"),
    ("telecom", r"оператор\w* связи"),
    ("finance", r"банк|кредит|займ|мфо|финанс|инвест|цифров\w+ валют|перевод\w* денеж|рассрочк|платёжн|платежн|115-фз"),
    ("gov", r"гос|муницип|\bгис\b"),
)
SECTOR_EVIDENCE = {
    "medical": ["feature:sector.medical", "okved:86", "owner_confirms"],
    "finance": ["feature:sector.finance", "registry:Банк России", "owner_confirms"],
    "education": ["feature:sector.education_courses", "okved:85", "owner_confirms"],
    "gambling": ["feature:sector.gambling", "owner_confirms"],
    "alcohol-tobacco": ["feature:sector.alcohol_tobacco", "owner_confirms"],
    "gov": ["feature:sector.gov", "okved:84", "owner_confirms"],
    "taxi-tourism": ["feature:sector.taxi_tourism", "owner_confirms"],
    "telecom": ["okved:61", "owner_confirms"],
    "kii": ["owner_confirms"],
    "other": ["owner_confirms"],
}

ALWAYS_RE = re.compile(r"любой|любая|оператор пдн|сбор пдн|владелец сайта")
MINORS_RE = re.compile(r"младше 18|несовершеннолет")
REVENUE_RE = re.compile(r"выручк")
DOMAIN_RE = re.compile(r"домен в зоне")
B2C_RE = re.compile(r"b2c|потребител")


class SeedError(Exception):
    """Input missing or malformed."""


def load_requirements(kb: Path) -> list:
    path = kb / "requirements.jsonl"
    if not path.is_file():
        raise SeedError(f"requirements.jsonl not found in {kb}")
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise SeedError(f"{path}: {error}") from error


def load_catalog(path: Path) -> set:
    if not path.is_file():
        raise SeedError(f"catalog not found: {path}")
    try:
        return {entry["id"] for entry in json.loads(path.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SeedError(f"{path}: {error}") from error


def load_triggers(build_refs, records: list) -> dict:
    """slug -> short trigger: from the source base's table module if --build-refs is given, else from the records."""
    triggers = {r["id"].split(":", 1)[1]: r.get("trigger", "") for r in records}
    if build_refs:
        from kb.legacy import load_build_refs  # build-time only; nothing is copied
        try:
            refs = load_build_refs(build_refs)
        except (FileNotFoundError, AttributeError) as error:
            raise SeedError(str(error)) from error
        triggers.update({slug: text for slug, text in refs.TRIGGER.items() if slug in triggers})
    return triggers


def sector_of(text: str) -> str:
    for name, pattern in SECTOR_RULES:
        if re.search(pattern, text):
            return name
    return "other"


def seed(records: list, catalog: set, triggers: dict) -> dict:
    always, features, facts, sectors, not_detectable, platform = set(), {}, {}, {}, {}, set()

    def add(table, key, rid):
        table.setdefault(key, set()).add(rid)

    for r in records:
        rid = r["id"]
        slug = rid.split(":", 1)[1]
        text = " | ".join((triggers.get(slug, ""), r.get("title", ""), r.get("summary", ""))).lower()
        trigger = triggers.get(slug, "").lower()
        if r.get("source_kind") == "store-policy":
            platform.add(rid)
        if r.get("obligation") == "sectoral":
            add(sectors, sector_of(text), rid)
            continue
        placed = False
        if r.get("obligation") == "general" and ALWAYS_RE.search(trigger):
            always.add(rid)
            placed = True
        subjects = r.get("subjects") or []
        if subjects in (["npd"], ["foreign"]):
            add(facts, "subject:" + subjects[0], rid)
            placed = True
        if MINORS_RE.search(trigger):
            add(facts, "minors", rid)
            placed = True
        if REVENUE_RE.search(trigger):
            add(facts, "revenue_over_20m", rid)
            placed = True
        if DOMAIN_RE.search(trigger):
            add(facts, "domain_ru", rid)
            placed = True
        if (r.get("models") or []) == ["b2c"] and B2C_RE.search(trigger) and not placed:
            add(facts, "b2c", rid)
            placed = True
        for feature, pattern in FEATURE_RULES.items():
            if feature in catalog and re.search(pattern, text):
                add(features, feature, rid)
                placed = True
        if r.get("source_kind") == "store-policy" and "mobile.app" in catalog:
            add(features, "mobile.app", rid)
            placed = True
        if not placed:
            not_detectable[rid] = "seed: no keyword rule matched; decide by hand from the card"

    return {
        "_doc": "Draft seeded by tools/seed_feature_map.py from keyword rules. Curate every link by hand "
                "against the card before copying anything into feature-map.json.",
        "always": sorted(always),
        "features": {k: sorted(v) for k, v in sorted(features.items())},
        "owner_facts": {k: sorted(v) for k, v in sorted(facts.items())},
        "sectoral": {
            name: {"evidence": SECTOR_EVIDENCE[name], "requirements": sorted(ids)}
            for name, ids in sorted(sectors.items())
        },
        "not_detectable": dict(sorted(not_detectable.items())),
        "notes": {},
        "platform_rules": sorted(platform),
        "templates": {},
        "documents": {},
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Seed a draft feature map (never the curated one).")
    parser.add_argument("--out", required=True, help="draft output path ('-' for stdout)")
    parser.add_argument("--kb", default=str(DEFAULT_KB), help="jurisdiction pack with requirements.jsonl")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="features/catalog.json")
    parser.add_argument("--build-refs", help="the source base's build_refs.py: take the short triggers from it")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    kb = Path(args.kb)
    if args.out != "-" and Path(args.out).name == CURATED_NAME and Path(args.out).resolve().parent == kb.resolve():
        print(f"refusing to overwrite the curated {CURATED_NAME}; write the draft elsewhere", file=sys.stderr)
        return 2
    try:
        records = load_requirements(kb)
        catalog = load_catalog(Path(args.catalog))
        draft = seed(records, catalog, load_triggers(args.build_refs, records))
    except SeedError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    text = json.dumps(draft, ensure_ascii=False, indent=2) + "\n"
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
