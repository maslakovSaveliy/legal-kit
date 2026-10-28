#!/usr/bin/env python3
"""Select the requirements that apply to a product. Python 3.9+, standard library only.

Reads <kb>/requirements.jsonl, <kb>/feature-map.json, <kb>/documents/*.md and, optionally,
.legal/answers.json (canonical schema in owner-questions.md). The applicable set is
always + detected features + owner facts + sectors passed explicitly (confirmed), then
narrowed by the requirement's subjects/models/products. A requirement with obligation
"sectoral" applies only with a confirmed sector. Templates and documents come from the map's
"templates" / "documents" sections (always, or a listed feature found, or a listed fact true; a rule
does not fire when a feature of its optional "without" list is found, and fires only for products of
its optional "products" list when the product kinds are known);
without those sections they fall back to the requirements' own `templates` and to the ids named
in documents/*.md, with a warning on stderr. `not_detectable` lists requirements that appear only
in the map's not_detectable section (owner checklist). --planned takes features the owner described
(plan and feature modes) with reasons "planned:<id>"; they are never read from answers.json.
"feature_sources" says for every feature whether it was found, planned or both. Prints JSON.

Exit codes: 0 ok, 2 bad input.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _kb  # noqa: E402  (must come first: it protects the stdlib `select` module)

import argparse  # noqa: E402
import glob  # noqa: E402
import re  # noqa: E402

ID_RE = re.compile(r"\b[a-z]{2,}:[a-z0-9][a-z0-9-]*")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="select.py",
        description="Select applicable requirements from a jurisdiction pack. Prints JSON.")
    parser.add_argument("--kb", default=_kb.DEFAULT_KB, help="jurisdiction pack directory (default: bundled ru)")
    parser.add_argument("--features", help="comma-separated feature ids found by the scanners")
    parser.add_argument("--planned", help="comma-separated feature ids the owner described (plan and feature modes)")
    parser.add_argument("--subject", help="owner status: " + "|".join(_kb.SUBJECTS))
    parser.add_argument("--models", help="comma-separated: " + ",".join(_kb.MODELS))
    parser.add_argument("--products", help="comma-separated: " + ",".join(_kb.PRODUCTS))
    parser.add_argument("--sectors", help="comma-separated CONFIRMED sectors (sectoral requirements need one)")
    parser.add_argument("--facts", help="extra owner facts, e.g. minors,revenue_over_20m,subject:npd")
    parser.add_argument("--answers", help=".legal/answers.json; flags override its values")
    parser.add_argument("--today", help="YYYY-MM-DD (default: today)")
    return parser


def _check(values, allowed, label):
    bad = [v for v in values if v not in allowed]
    if bad:
        raise _kb.KbError("unknown %s %s; allowed: %s" % (label, ", ".join(bad), ", ".join(allowed)))
    return values


RU_ZONES = (".ru", ".xn--p1ai", ".su")


def _is_ru_domain(url):
    """True for a product URL whose host ends in .ru, .рф (xn--p1ai) or .su."""
    if not isinstance(url, str):
        return False
    host = _kb.url_host(url if "://" in url else "https://" + url)
    return bool(host) and host.endswith(RU_ZONES)


def resolve_inputs(args):
    """Merge flags and answers.json into the selection inputs (flags win)."""
    answers = _kb.load_answers(args.answers) if args.answers else {}
    owner, audience, business, product = _kb.answers_sections(answers, args.answers)

    subject = args.subject if args.subject is not None else owner.get("status")
    if subject:
        _check([subject], _kb.SUBJECTS, "subject")
    else:
        subject = None

    models = _kb.csv_list(args.models)
    if models is None:
        models = [m for m in _kb.MODELS if audience.get(m) is True]
    products = _kb.csv_list(args.products)
    if products is None:
        products = [p for p in (product.get("kinds") or [])]
    sectors = _kb.csv_list(args.sectors)
    if sectors is None:
        sectors = [s for s in (business.get("sectors") or [])]
    _check(models, _kb.MODELS, "model")
    _check(products, _kb.PRODUCTS, "product")

    facts = set()
    if subject:
        facts.add("subject:" + subject)
    if "b2c" in models:
        facts.add("b2c")
    if audience.get("minors") in ("14-18", "under-14"):
        facts.add("minors")
    if business.get("revenue_over_20m") is True:
        facts.add("revenue_over_20m")
    if any(_is_ru_domain(url) for url in product.get("urls") or []):
        facts.add("domain_ru")
    facts.update(_kb.csv_list(args.facts) or [])

    return {
        "features": _kb.csv_list(args.features) or [],
        "planned": list(dict.fromkeys(_kb.csv_list(args.planned) or [])),
        "subject": subject,
        "models": sorted(set(models)),
        "products": sorted(set(products)),
        "sectors": sorted(set(sectors)),
        "facts": sorted(facts),
    }


def candidates(fmap, inputs, warnings):
    """id -> list of reasons it entered the candidate set."""
    why = {}

    def add(ids, reason):
        for req_id in ids or []:
            reasons = why.setdefault(req_id, [])
            if reason not in reasons:
                reasons.append(reason)

    add(fmap.get("always"), "always")
    features = fmap.get("features") or {}
    for prefix, key in (("feature:", "features"), ("planned:", "planned")):
        for feature in inputs.get(key, []):
            if feature in features:
                add(features[feature], prefix + feature)
            else:
                warnings.append("feature %s is not in feature-map.json" % feature)
    owner_facts = fmap.get("owner_facts") or {}
    for fact in inputs["facts"]:
        add(owner_facts.get(fact), "owner:" + fact)
    sectoral = fmap.get("sectoral") or {}
    for sector in inputs["sectors"]:
        entry = sectoral.get(sector)
        if entry is None:
            warnings.append("sector %s is not in feature-map.json" % sector)
        else:
            add(entry.get("requirements"), "sector:" + sector)
    return why


def filter_reasons(requirement, inputs):
    """Why a candidate does not fit the product (empty list: it fits)."""
    reasons = []
    subjects = requirement.get("subjects") or []
    if inputs["subject"] and subjects and inputs["subject"] not in subjects:
        reasons.append("subject %s not in %s" % (inputs["subject"], ",".join(subjects)))
    for field, key in (("models", "models"), ("products", "products")):
        allowed = requirement.get(field) or []
        wanted = inputs[key]
        if wanted and allowed and not set(wanted) & set(allowed):
            reasons.append("%s %s not in %s" % (field, ",".join(wanted), ",".join(allowed)))
    return reasons


def documents_by_ids(kb, applicable_ids):
    """Fallback: documents/*.md whose spec names an applicable requirement id."""
    found = []
    pattern = os.path.join(str(kb), "documents", "*.md")
    for path in sorted(glob.glob(pattern)):
        matched = sorted(set(ID_RE.findall(_kb.read_text(path))) & applicable_ids)
        if matched:
            name = os.path.splitext(os.path.basename(path))[0]
            found.append({"name": name, "path": "documents/%s.md" % name, "requirements": matched})
    return found


def mapped(section, inputs):
    """Names from a map section {name: {features, facts, always, without, products}} that apply, with the reason."""
    present = set(inputs["features"])
    planned = set(inputs.get("planned", [])) - present
    facts = set(inputs["facts"]) | set(inputs["sectors"]) | {"sector:" + s for s in inputs["sectors"]}
    chosen = []
    for name in sorted(section):
        rule = section[name] if isinstance(section[name], dict) else {}
        if (present | planned) & set(rule.get("without") or []):
            continue
        if rule.get("products") and inputs["products"] and not set(inputs["products"]) & set(rule["products"]):
            continue
        why = []
        if rule.get("always"):
            why.append("always")
        why.extend("feature:" + f for f in rule.get("features") or [] if f in present)
        why.extend("planned:" + f for f in rule.get("features") or [] if f in planned)
        why.extend("fact:" + f for f in rule.get("facts") or [] if f in facts)
        if why:
            chosen.append((name, why))
    return chosen


def select(kb, inputs, today):
    requirements = _kb.load_requirements(kb)
    fmap = _kb.load_feature_map(kb)
    warnings = []
    why = candidates(fmap, inputs, warnings)
    notes = fmap.get("notes") if isinstance(fmap.get("notes"), dict) else {}

    applicable, not_applicable = [], []
    for req_id in sorted(why):
        requirement = requirements.get(req_id)
        if requirement is None:
            warnings.append("feature-map.json refers to unknown requirement %s" % req_id)
            continue
        reasons = filter_reasons(requirement, inputs)
        if requirement.get("obligation") == "sectoral" and not any(r.startswith("sector:") for r in why[req_id]):
            reasons.append("sectoral: no confirmed sector")
        if reasons:
            not_applicable.append({"id": req_id, "reason": "; ".join(reasons)})
            continue
        latest = _kb.latest_requirement_date(requirement)
        future = latest.isoformat() if latest and latest > today else None
        applicable.append({"id": req_id, "why": why[req_id], "future_from": future, "note": notes.get(req_id)})

    applicable_ids = {item["id"] for item in applicable}
    if isinstance(fmap.get("templates"), dict) and isinstance(fmap.get("documents"), dict):
        templates = [{"name": name, "why": reasons} for name, reasons in mapped(fmap["templates"], inputs)]
        documents = []
        by_ids = {d["name"]: d["requirements"] for d in documents_by_ids(kb, applicable_ids)}
        for name, reasons in mapped(fmap["documents"], inputs):
            documents.append({"name": name, "path": "documents/%s.md" % name, "why": reasons,
                              "requirements": by_ids.get(name, [])})
    else:
        warning = ("feature-map.json has no \"templates\"/\"documents\" sections: templates and documents "
                   "follow the requirements' own template lists and the ids named in documents/*.md")
        warnings.append(warning)
        sys.stderr.write("select.py: " + warning + "\n")
        templates = [{"name": name, "why": ["requirement"]} for name in sorted(
            {t for i in applicable_ids for t in requirements[i].get("templates") or []})]
        documents = documents_by_ids(kb, applicable_ids)

    owner_questions = sorted(i for i in applicable_ids if requirements[i].get("cannot_check"))
    detectable = set(why)
    not_detectable = []
    for req_id, reason in sorted((fmap.get("not_detectable") or {}).items()):
        requirement = requirements.get(req_id)
        if req_id in detectable or requirement is None or filter_reasons(requirement, inputs):
            continue
        not_detectable.append({"id": req_id, "reason": reason})
    sources = {}
    for key, label in (("features", "found"), ("planned", "planned")):
        for feature in inputs.get(key, []):
            sources.setdefault(feature, set()).add(label)
    return {
        "inputs": dict(inputs, today=today.isoformat()),
        "feature_sources": {f: sorted(labels) for f, labels in sorted(sources.items())},
        "applicable": applicable,
        "not_applicable": not_applicable,
        "templates": [t["name"] for t in templates],
        "template_reasons": {t["name"]: t["why"] for t in templates},
        "documents": documents,
        "owner_questions": owner_questions,
        "not_detectable": not_detectable,
        "warnings": warnings,
    }


def main(argv=None):
    args, code = _kb.parse_args(build_parser(), sys.argv[1:] if argv is None else argv)
    if args is None:
        return code
    try:
        inputs = resolve_inputs(args)
        today = _kb.today_arg(args.today)
        result = select(args.kb, inputs, today)
    except _kb.KbError as exc:
        return _kb.fail(str(exc))
    _kb.emit(result)
    return 0


if __name__ == "__main__":
    _kb.setup_stdio()
    sys.exit(main())
