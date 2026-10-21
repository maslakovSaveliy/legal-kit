#!/usr/bin/env python3
"""Verify and render .legal/report.json. Python 3.9+, standard library only.

    report.py verify R --kb K [--sources S] [--answers A] [--today D]
    report.py render R [--kb K] [--lang ru|en]

Report shape: {"version": 1, "generated": "...", "lang": "ru|en", "product": {...},
"mode": "repo+prod|prod-only|repo-only", "rows": [...], "registries": [{name, status, url, note}],
"not_checked": [...], "owner_checklist": [...] (optional)}. All keys but lang and owner_checklist are
required. A row has req, title, status, evidence, norm, level, confidence,
effective_from, source, sources, bucket, element ("<template>:<id>" or null) and basis. Evidence is a list
of {file, line} or {url}, each with an optional string "note" (for example «до правок» for a baseline line).

verify prints a JSON list of issues ({row, req, rule, message}; sources.json problems carry
"source" instead of "row", top-level problems have "row": null and a "key") and exits 1 when it is not
empty. Rules: missing_field, bad_enum, bad_type, unknown_req, unknown_element, element_req_mismatch,
mandatory_unsupported, conditional_unsupported, level_basis_mismatch, platform_level, source_required,
source_not_allowlisted, missing_evidence, future_not_roadmap, effective_from_unknown, sectoral_unconfirmed.
With --answers (.legal/answers.json) a mandatory or conditional row of a sectoral requirement (status not n_a)
needs a sector group in business.sectors whose feature-map.json entry lists that requirement; without the flag
the rule is off.
render prints Markdown (sections by bucket, rows grouped by requirement direction).

Reads the jurisdiction pack (requirements.jsonl, elements.json, BASE.md). Exit codes: 0 ok, 1 verify
found issues, 2 bad input.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _kb  # noqa: E402  (must come first: it protects the stdlib `select` module)

import argparse  # noqa: E402

ENUMS = {
    "status": ("present", "missing", "partial", "not_visible", "n_a"),
    "level": ("mandatory", "conditional", "recommended", "interpretation"),
    "confidence": ("high", "medium", "low"),
    "source": ("base", "official_runtime", "market", "platform"),
    "bucket": ("done", "owner", "disputed", "roadmap"),
    "basis": ("norm", "practice", "interpretation", "inference", "platform"),
}
REQUIRED = ("req", "title", "status", "level", "confidence", "source", "bucket", "basis")
NEEDS_EVIDENCE = ("present", "missing", "partial")
MANDATORY_SOURCES = ("base", "official_runtime")
MANDATORY_KINDS = ("law", "bylaw")
SOURCE_KINDS = ("official", "market", "platform")


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------

TOP_REQUIRED = ("version", "generated", "product", "mode", "rows", "registries", "not_checked")
MODES = ("repo+prod", "prod-only", "repo-only")
LANGS = ("ru", "en")
REGISTRY_STATUSES = ("ok", "not_found", "manual", "error")
OBLIGATION_LEVELS = ("mandatory", "conditional")
SOFT_LEVELS = ("recommended", "interpretation")
ELEMENT_STATUS_FOR = {"mandatory": ("обязательно",), "conditional": ("обязательно", "при условии")}


def load_report(path):
    data = _kb.load_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise _kb.KbError("%s must be an object with a \"rows\" list" % path)
    return data


def valid_evidence(item):
    return isinstance(item, dict) and any(isinstance(item.get(key), str) and item[key] for key in ("file", "url"))


def is_str_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def verify_top(report):
    """Issues about the top-level keys (row is None)."""
    issues = []

    def issue(rule, message, key):
        issues.append({"row": None, "req": None, "rule": rule, "key": key, "message": message})

    for key in TOP_REQUIRED:
        if key not in report:
            issue("missing_field", "report has no %r" % key, key)
    if "version" in report and not (type(report["version"]) is int and report["version"] == 1):
        issue("bad_enum", "version must be the integer 1, got %r" % (report["version"],), "version")
    if "generated" in report and not isinstance(report["generated"], str):
        issue("bad_type", "generated must be a string", "generated")
    if "product" in report and not isinstance(report["product"], dict):
        issue("bad_type", "product must be an object", "product")
    if "mode" in report and report["mode"] not in MODES:
        issue("bad_enum", "mode %r is not one of %s" % (report["mode"], "|".join(MODES)), "mode")
    if "lang" in report and report["lang"] not in LANGS:
        issue("bad_enum", "lang %r is not one of %s" % (report["lang"], "|".join(LANGS)), "lang")
    if "registries" in report:
        if not isinstance(report["registries"], list):
            issue("bad_type", "registries must be a list", "registries")
        else:
            for number, entry in enumerate(report["registries"]):
                if not isinstance(entry, dict) or entry.get("status") not in REGISTRY_STATUSES:
                    issue("bad_enum", "registries[%d] needs an object with status %s" % (
                        number, "|".join(REGISTRY_STATUSES)), "registries")
    for key in ("not_checked", "owner_checklist"):
        if key in report and not is_str_list(report[key]):
            issue("bad_type", "%s must be a list of strings" % key, key)
    return issues


def confirmed_sectoral_ids(answers_path, kb):
    """Requirement ids of the sector groups the owner confirmed (business.sectors of answers.json)."""
    _, _, business, _ = _kb.answers_sections(_kb.load_answers(answers_path), source=str(answers_path))
    sectoral = _kb.load_feature_map(kb).get("sectoral")
    sectoral = sectoral if isinstance(sectoral, dict) else {}
    ids = set()
    for group in business.get("sectors") or []:
        entry = sectoral.get(group)
        if isinstance(entry, dict):
            ids.update(i for i in entry.get("requirements") or [] if isinstance(i, str))
    return ids


def verify_row(index, row, requirements, elements, today, sectoral_ids=None):
    """Issues of one row; sectoral_ids (confirmed sectoral requirement ids) switches the sector gate on."""
    issues = []

    def issue(rule, message):
        issues.append({"row": index, "req": row.get("req") if isinstance(row.get("req"), str) else None,
                       "rule": rule, "message": message})

    for field in REQUIRED:
        if field not in row:
            issue("missing_field", "row has no %r" % field)
    typed_ok = True
    for field in ("req", "element", "norm", "effective_from"):
        if row.get(field) is not None and not isinstance(row[field], str):
            issue("bad_type", "%s must be a string or null" % field)
            typed_ok = False
    if "title" in row and not isinstance(row["title"], str):
        issue("bad_type", "title must be a string")
    if row.get("sources") is not None and not is_str_list(row["sources"]):
        issue("bad_type", "sources must be a list of URL strings")
        typed_ok = False
    if row.get("evidence") is not None and not (isinstance(row["evidence"], list)
                                                and all(isinstance(e, dict) for e in row["evidence"])):
        issue("bad_type", "evidence must be a list of objects")
        typed_ok = False
    elif any(e.get("note") is not None and not isinstance(e["note"], str) for e in row.get("evidence") or []):
        issue("bad_type", "evidence note must be a string (for example «до правок»)")
    for field, allowed in ENUMS.items():
        value = row.get(field)
        if field in row and (not isinstance(value, str) or value not in allowed):
            issue("bad_enum", "%s %r is not one of %s" % (field, value, "|".join(allowed)))
    if not typed_ok:
        return issues

    row_date = None
    if row.get("effective_from") is not None:
        row_date = _kb.parse_date(row["effective_from"])
        if row_date is None:
            issue("bad_enum", "effective_from %r must be YYYY-MM-DD or null" % (row["effective_from"],))

    requirement = None
    req_id = row.get("req")
    if req_id is not None:
        requirement = requirements.get(req_id)
        if requirement is None:
            issue("unknown_req", "%r is not a requirement of this knowledge base" % (req_id,))
    element = None
    element_id = row.get("element")
    if element_id is not None:
        element = elements.get(element_id)
        if element is None:
            issue("unknown_element", "%r is not an element of this knowledge base (<template>:<id>)" % (element_id,))
        elif req_id is not None and req_id not in (element.get("requirements") or []):
            issue("element_req_mismatch", "element %s does not belong to requirement %s" % (element_id, req_id))

    level, source, basis = row.get("level"), row.get("source"), row.get("basis")
    if level in OBLIGATION_LEVELS:
        missing = []
        if basis != "norm":
            missing.append("basis must be norm")
        if source not in MANDATORY_SOURCES:
            missing.append("source must be base or official_runtime")
        if requirement is None:
            missing.append("a known requirement is needed")
        else:
            if requirement.get("source_kind") not in MANDATORY_KINDS:
                missing.append("requirement source_kind must be law or bylaw")
            if requirement.get("legal_confidence") == "low":
                missing.append("requirement legal_confidence is low")
        if element is not None:
            if element.get("status") not in ELEMENT_STATUS_FOR[level]:
                missing.append("element status must be %s" % " or ".join(ELEMENT_STATUS_FOR[level]))
            if element.get("method") != "norm":
                missing.append("element method is not norm")
        if missing:
            issue("mandatory_unsupported" if level == "mandatory" else "conditional_unsupported",
                  "level %s is not supported: %s" % (level, "; ".join(missing)))
    if (sectoral_ids is not None and requirement is not None and requirement.get("obligation") == "sectoral"
            and level in OBLIGATION_LEVELS and row.get("status") != "n_a" and req_id not in sectoral_ids):
        issue("sectoral_unconfirmed", "%s is a sector requirement and no sector confirmed in answers.json "
                                      "(business.sectors) lists it: confirm the sector with the owner, or lower the "
                                      "row to interpretation, or set status n_a" % req_id)
    if level in ENUMS["level"] and level not in SOFT_LEVELS and (
            basis in ("interpretation", "practice", "inference") or source == "market"):
        issue("level_basis_mismatch", "basis %s / source %s may only carry level recommended or interpretation"
              % (basis, source))

    if (source == "platform" or basis == "platform") and level not in SOFT_LEVELS:
        issue("platform_level", "store and platform rules are never mandatory or conditional-as-law: "
                                "use level recommended or interpretation")

    urls = row.get("sources") or []
    if source in ("official_runtime", "platform"):
        check, where = (_kb.is_allowlisted, "the official-source allowlist") if source == "official_runtime" else (
            _kb.is_platform_url, "the platform domains")
        if not urls:
            issue("source_required", "source %s needs at least one URL in sources" % source)
        for url in urls:
            if not check(url):
                issue("source_not_allowlisted", "%s is not on %s" % (url, where))

    if row.get("status") in NEEDS_EVIDENCE:
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(valid_evidence(e) for e in evidence):
            issue("missing_evidence", "status %s needs evidence: a list of {file, line} or {url}" % row["status"])

    flagged_future = False
    if requirement is not None:
        own_date = _kb.single_effective_date(requirement)
        if own_date is not None and own_date > today and row.get("bucket") != "roadmap":
            flagged_future = True
            issue("future_not_roadmap", "the requirement applies from %s, after %s: bucket must be roadmap"
                  % (own_date.isoformat(), today.isoformat()))
        if row_date is not None and row_date not in _kb.requirement_dates(requirement):
            issue("effective_from_unknown", "effective_from %s is not a date of the requirement (%s)" % (
                row_date.isoformat(), ", ".join(sorted(d.isoformat() for d in _kb.requirement_dates(requirement)))
                or "none"))
        if row.get("effective_from") is None:
            row_date = _kb.latest_requirement_date(requirement)
    if row_date is not None and row_date > today and row.get("bucket") != "roadmap" and not flagged_future:
        issue("future_not_roadmap", "applies from %s, which is after %s: put it in the roadmap bucket"
              % (row_date.isoformat(), today.isoformat()))
    return issues


def verify_sources(path):
    data = _kb.load_json(path)
    if not isinstance(data, list):
        raise _kb.KbError("%s must hold a list" % path)
    issues = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            issues.append({"row": None, "source": index, "rule": "bad_enum", "message": "entry is not an object"})
            continue
        kind = entry.get("kind")
        url = entry.get("url")
        if kind not in SOURCE_KINDS:
            issues.append({"row": None, "source": index, "rule": "bad_enum",
                           "message": "kind %r is not one of %s" % (kind, "|".join(SOURCE_KINDS))})
        elif kind == "official" and not _kb.is_allowlisted(url):
            issues.append({"row": None, "source": index, "rule": "source_not_allowlisted", "url": url,
                           "message": "official source %s is not on the allowlist" % (url,)})
        elif kind == "platform" and not _kb.is_platform_url(url):
            issues.append({"row": None, "source": index, "rule": "source_not_allowlisted", "url": url,
                           "message": "platform source %s is not on the platform domains" % (url,)})
    return issues


def cmd_verify(args):
    report = load_report(args.report)
    today = _kb.today_arg(args.today)
    requirements = _kb.load_requirements(args.kb)
    elements = _kb.load_elements(args.kb)
    sectoral_ids = confirmed_sectoral_ids(args.answers, args.kb) if args.answers else None
    issues = verify_top(report)
    for index, row in enumerate(report["rows"]):
        if not isinstance(row, dict):
            issues.append({"row": index, "req": None, "rule": "bad_type", "message": "row is not an object"})
            continue
        issues.extend(verify_row(index, row, requirements, elements, today, sectoral_ids))
    if args.sources:
        issues.extend(verify_sources(args.sources))
    _kb.emit(issues)
    return 1 if issues else 0


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

DIRECTIONS = {
    "A": ("Субъекты и юрисдикция", "Subjects and jurisdiction"),
    "B": ("Персональные данные", "Personal data"),
    "C": ("Cookies, аналитика, SDK", "Cookies, analytics, SDKs"),
    "D": ("Регистрация и аутентификация", "Registration and authentication"),
    "E": ("Пользовательский контент и платформы", "User content and platforms"),
    "F": ("Торговля, платежи, подписки", "Commerce, payments, subscriptions"),
    "G": ("Реклама, рассылки, push", "Advertising, mailings, push"),
    "H": ("Информация для потребителей и язык", "Consumer information and language"),
    "I": ("Дети и особые аудитории", "Children and special audiences"),
    "J": ("Информационная безопасность", "Information security"),
    "K": ("Отраслевые требования", "Sector-specific requirements"),
    "L": ("Магазины приложений и предустановка", "App stores and preinstallation"),
    "M": ("Права владельца на контент и ПО", "Owner's rights to content and software"),
    "N": ("Новые технологии", "New technologies"),
}
OTHER = "?"

TEXT = {
    "ru": {
        "title": "Отчёт о юридической настройке", "product": "Продукт", "mode": "Режим", "date": "Дата",
        "base": "База требований", "summary": "Сводка по направлениям", "direction": "Направление",
        "other": "Прочее", "none": "Нет.", "registries": "Реестры", "not_checked": "Что не проверялось",
        "checklist": "Запрос документов",
        "disclaimer": "Не юридическая консультация.",
        "buckets": {"done": "Сделано", "owner": "Сделать вам", "disputed": "Спорно", "roadmap": "Дорожная карта"},
        "columns": ("Требование", "Статус", "Уровень", "Норма", "Уверенность", "Источник", "Доказательства"),
        "from": "С даты",
        "reg_columns": ("Реестр", "Статус", "Адрес", "Примечание"),
        "status": {"present": "есть", "missing": "нет", "partial": "частично", "not_visible": "не видно",
                   "n_a": "неприменимо"},
        "level": {"mandatory": "обязательно", "conditional": "при условии", "recommended": "рекомендуется",
                  "interpretation": "трактовка"},
        "source": {"base": "база", "official_runtime": "официальный источник", "market": "практика рынка",
                   "platform": "правила платформы"},
        "confidence": {"high": "высокая", "medium": "средняя", "low": "низкая"},
    },
    "en": {
        "title": "Legal setup report", "product": "Product", "mode": "Mode", "date": "Date",
        "base": "Requirements base", "summary": "Summary by direction", "direction": "Direction",
        "other": "Other", "none": "None.", "registries": "Registries", "not_checked": "Not checked",
        "checklist": "Documents to provide",
        "disclaimer": "Not legal advice.",
        "buckets": {"done": "Done", "owner": "To do (owner)", "disputed": "Disputed", "roadmap": "Roadmap"},
        "columns": ("Requirement", "Status", "Level", "Norm", "Confidence", "Source", "Evidence"),
        "from": "From",
        "reg_columns": ("Registry", "Status", "Address", "Note"),
        "status": {"present": "present", "missing": "missing", "partial": "partial", "not_visible": "not visible",
                   "n_a": "not applicable"},
        "level": {"mandatory": "mandatory", "conditional": "conditional", "recommended": "recommended",
                  "interpretation": "interpretation"},
        "source": {"base": "knowledge base", "official_runtime": "official source", "market": "market practice",
                   "platform": "platform rules"},
        "confidence": {"high": "high", "medium": "medium", "low": "low"},
    },
}


def cell(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip() or "—"


def table(columns, rows):
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines.extend("| " + " | ".join(cell(c) for c in row) + " |" for row in rows)
    return lines


def as_text(value):
    """Any report value as display text: render must survive a hand-edited or wrongly typed report."""
    return value if isinstance(value, str) else ("" if value is None else str(value))


def as_list(value):
    return value if isinstance(value, list) else []


def label(mapping, value):
    return mapping.get(value, value) if isinstance(value, str) else as_text(value)


def evidence_text(row):
    parts = []
    for item in as_list(row.get("evidence")):
        if isinstance(item, dict):
            if item.get("file"):
                text = "%s:%s" % (item["file"], item["line"]) if item.get("line") else item["file"]
            elif item.get("url"):
                text = item["url"]
            else:
                continue
            note = item.get("note")
            parts.append("%s (%s)" % (text, note) if isinstance(note, str) and note else text)
    return "; ".join(parts)


def direction_of(row, requirements):
    req = row.get("req")
    requirement = requirements.get(req) if isinstance(req, str) else None
    letter = requirement.get("dir") if requirement else None
    return letter if letter in DIRECTIONS else OTHER


def direction_title(letter, lang, text):
    if letter == OTHER:
        return text["other"]
    return "%s. %s" % (letter, DIRECTIONS[letter][0 if lang == "ru" else 1])


def render(report, requirements, base, lang):
    text = TEXT[lang]
    rows = [r for r in report["rows"] if isinstance(r, dict)]
    product = report.get("product") if isinstance(report.get("product"), dict) else {}
    kinds = ", ".join(as_text(k) for k in as_list(product.get("kinds")))
    urls = " ".join(as_text(u) for u in as_list(product.get("urls")))
    order = sorted({direction_of(r, requirements) for r in rows}, key=lambda d: (d == OTHER, d))
    out = ["# %s: %s" % (text["title"], as_text(product.get("name")) or "—"), ""]
    details = [(text["product"], ", ".join(filter(None, [kinds, urls])) or "—"),
               (text["mode"], as_text(report.get("mode")) or "—"),
               (text["date"], as_text(report.get("generated")) or "—")]
    out.extend("- %s: %s" % pair for pair in details)
    out.append("")
    if base:
        out.extend(["%s: %s" % (text["base"], base), ""])

    out.extend(["## " + text["summary"], ""])
    head = [text["direction"]] + [text["buckets"][b] for b in ("done", "owner", "disputed", "roadmap")]
    counts = []
    for letter in order:
        in_dir = [r for r in rows if direction_of(r, requirements) == letter]
        counts.append([direction_title(letter, lang, text)] + [sum(1 for r in in_dir if r.get("bucket") == b)
                                                               for b in ("done", "owner", "disputed", "roadmap")])
    out.extend(table(head, counts) if counts else [text["none"]])
    out.append("")

    for bucket in ("done", "owner", "disputed", "roadmap"):
        out.extend(["## " + text["buckets"][bucket], ""])
        in_bucket = [r for r in rows if r.get("bucket") == bucket]
        if not in_bucket:
            out.extend([text["none"], ""])
            continue
        columns = text["columns"] + ((text["from"],) if bucket == "roadmap" else ())
        for letter in order:
            group = [r for r in in_bucket if direction_of(r, requirements) == letter]
            if not group:
                continue
            out.extend(["### " + direction_title(letter, lang, text), ""])
            body = []
            for r in group:
                title = as_text(r.get("title")) or "—"
                if isinstance(r.get("req"), str) and r["req"]:
                    title += " (`%s`)" % r["req"]
                line = [title, label(text["status"], r.get("status")), label(text["level"], r.get("level")),
                        r.get("norm"), label(text["confidence"], r.get("confidence")),
                        label(text["source"], r.get("source")), evidence_text(r)]
                if bucket == "roadmap":
                    line.append(r.get("effective_from"))
                body.append(line)
            out.extend(table(columns, body))
            out.append("")

    out.extend(["## " + text["registries"], ""])
    registries = [r for r in as_list(report.get("registries")) if isinstance(r, dict)]
    if registries:
        reg_rows = [(r.get("name"), r.get("status"), r.get("url"), r.get("note")) for r in registries]
        out.extend(table(text["reg_columns"], reg_rows))
    else:
        out.append(text["none"])
    checklist = [as_text(item) for item in as_list(report.get("owner_checklist"))]
    if checklist:
        out.extend(["", "## " + text["checklist"], ""])
        out.extend("- " + item for item in checklist)
    out.extend(["", "## " + text["not_checked"], ""])
    unchecked = [as_text(item) for item in as_list(report.get("not_checked"))]
    out.extend(["- " + item for item in unchecked] if unchecked else [text["none"]])
    out.extend(["", text["disclaimer"], ""])
    return "\n".join(out)


def cmd_render(args):
    report = load_report(args.report)
    lang = args.lang or report.get("lang") or "ru"
    if lang not in TEXT:
        raise _kb.KbError("lang must be ru or en, got %r" % (lang,))
    requirements = _kb.load_requirements(args.kb)
    sys.stdout.write(render(report, requirements, _kb.base_date(args.kb), lang))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="report.py", description="Verify and render .legal/report.json.")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="check a report against the knowledge base; prints a JSON list of issues")
    verify.add_argument("report")
    verify.add_argument("--kb", default=_kb.DEFAULT_KB, help="jurisdiction pack directory (default: bundled ru)")
    verify.add_argument("--sources", help=".legal/sources.json")
    verify.add_argument("--answers", help=".legal/answers.json: turns on the check that sector requirements "
                                          "rest on a sector the owner confirmed")
    verify.add_argument("--today", help="YYYY-MM-DD (default: today)")
    verify.set_defaults(run=cmd_verify)
    render_parser = sub.add_parser("render", help="render a report as Markdown")
    render_parser.add_argument("report")
    render_parser.add_argument("--kb", default=_kb.DEFAULT_KB, help="jurisdiction pack directory (default: bundled ru)")
    render_parser.add_argument("--lang", choices=sorted(TEXT), help="default: the report's \"lang\", else ru")
    render_parser.set_defaults(run=cmd_render)
    return parser


def main(argv=None):
    args, code = _kb.parse_args(build_parser(), sys.argv[1:] if argv is None else argv)
    if args is None:
        return code
    try:
        return args.run(args)
    except _kb.KbError as exc:
        return _kb.fail(str(exc))


if __name__ == "__main__":
    _kb.setup_stdio()
    sys.exit(main())
