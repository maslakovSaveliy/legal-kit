#!/usr/bin/env python3
"""Check drafted legal documents and public pages before they are handed over. Python 3.9+, standard library only.

    check_docs.py DRAFT... [--public PAGE]... [--answers .legal/answers.json] [--kb K] [--kind auto|offer|other]

Positional files, listed before the options, are drafts for the owner (.legal/drafts/); each --public FILE (the
flag once per file) is a public page or a project file that renders legal text (pages, footer, catalogs, paste
artifacts). Reads optionally .legal/answers.json
(schema: owner-questions.md, section "Схема answers.json") and <kb>/forbidden-clauses.json. Prints
{"files", "public", "issues", "summary", "blocking"}; every issue has file, line, kind and blocking:

  placeholder_requisite  leftover {{NAME}} of a requisite (name, INN, OGRN, address, e-mail, phone, ...)
  placeholder_runtime    leftover {{NAME}} of a per-user or per-order value (buyer's name, order number, ...)
  placeholder_fact       leftover {{NAME}} of anything else (retention, hosting region, recipients, hours, ...)
  condition              leftover [если ...], [Если ...], [вставьте ...] or [... :] marker
  inn_checksum           INN next to "ИНН" with a wrong length or check digit
  ogrn_checksum          OGRN/OGRNIP next to "ОГРН"/"ОГРНИП" with a wrong length or check digit
  mismatch               INN, OGRN or owner name differs from answers.json (or is not confirmed there)
  forbidden_clause       an offer contains a clause from forbidden-clauses.json (severity violation|risk)

Blocking: placeholders in drafts never block; in a public file every placeholder blocks except a requisite
listed in answers.json owner.withheld (a runtime one must become the project's own interpolation). A forbidden clause blocks with severity violation, not with risk.
Every other kind blocks.

Exit codes: 0 no blocking issue, 1 blocking issues found, 2 bad input.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _kb  # noqa: E402  (must come first: it protects the stdlib `select` module)

import argparse  # noqa: E402
import re  # noqa: E402

# A pack placeholder is a name with at least one Cyrillic letter: {{ИНН}}, {{EMAIL_ДЛЯ_ОБРАЩЕНИЙ}}. Template
# syntax in code ({{ color: 'red' }}, {{ LANGUAGE_CODE }}, {{ _('…') }}) is not a placeholder.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]*[А-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_]*)\s*\}\}")
# [если ...], [Если ...], [вставьте ...] (may continue on the next line) or a short "[label:]" marker
CONDITION_RE = re.compile(r"\[(?:[Ее]сли|[Вв]ставьте)\b[^\]\n]*\]?|(?:\[)[^\[\]\n]{1,80}:\](?!\()")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
# Placeholders of the pack that hold a requisite or an identity of the owner, built from the names and hints
# of placeholders.json («Реквизиты по статусу», registration, licence, the person responsible for personal
# data, a foreign company's registration). Everything else is a document fact.
REQUISITE_PLACEHOLDERS = frozenset((
    "НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА", "ИНН", "ОГРН_ИЛИ_ОГРНИП", "АДРЕС", "EMAIL_ДЛЯ_ОБРАЩЕНИЙ", "ТЕЛЕФОН",
    "EMAIL_ДЛЯ_ЗАЯВЛЕНИЙ_ПРАВООБЛАДАТЕЛЕЙ", "ОТВЕТСТВЕННЫЙ_ЗА_ОБРАБОТКУ_ПДН", "КОНТАКТЫ_ОТВЕТСТВЕННОГО",
    "СВЕДЕНИЯ_О_РЕГИСТРАЦИИ_ИП", "РЕГИСТРИРУЮЩИЙ_ОРГАН", "ВИД_ЛИЦЕНЗИРУЕМОЙ_ДЕЯТЕЛЬНОСТИ", "НОМЕР_ЛИЦЕНЗИИ",
    "СРОК_ЛИЦЕНЗИИ", "ЛИЦЕНЗИРУЮЩИЙ_ОРГАН", "ДАТА_ПРЕДОСТАВЛЕНИЯ_ЛИЦЕНЗИИ", "СТРАНА_РЕГИСТРАЦИИ",
    "РЕГИСТРАЦИОННЫЙ_НОМЕР",
))
# Placeholders filled per user, order or message at run time: the hint «Подставляются системой» of
# placeholders.json plus the per-user and per-order names of the confirmation, consent and mailing texts.
# On a page they become the project's own interpolation ({name}, ${name}, a template variable).
RUNTIME_PLACEHOLDERS = frozenset((
    "EMAIL_ПОЛЬЗОВАТЕЛЯ", "ДАТА_СОГЛАСИЯ", "ИСТОЧНИК_СОГЛАСИЯ", "КАНАЛ", "ТЕЛЕФОН_ПОЛЬЗОВАТЕЛЯ",
    "ИМЯ_ПОКУПАТЕЛЯ", "НОМЕР_ЗАКАЗА", "ДАТА_ЗАКАЗА", "СОСТАВ_ЗАКАЗА", "ЦЕНА_ЗАКАЗА", "ВЫБРАННЫЕ_ОПЦИИ",
    "СПОСОБ_И_АДРЕС_ДОСТАВКИ", "СПОСОБ_И_СТАТУС_ОПЛАТЫ", "ССЫЛКА_НА_ЗАКАЗ", "СТОИМОСТЬ_ДОСТАВКИ",
    "ИМЯ_ПОЛЬЗОВАТЕЛЯ", "НАЗВАНИЕ_УСЛУГИ", "ДАТА_И_ВРЕМЯ_ЗАПИСИ", "ЦЕНА_УСЛУГИ", "ОТМЕТКА_ОБ_ОПЛАТЕ_ИЛИ_АВАНСЕ",
    "ФИО_ПОЛЬЗОВАТЕЛЯ", "КОНТАКТЫ_ПОЛЬЗОВАТЕЛЯ", "ОТМЕЧЕННЫЕ_ПОЛЯ", "ЗАПРЕТЫ_И_УСЛОВИЯ_ПОЛЬЗОВАТЕЛЯ",
    "ДАТА_ПОЛУЧЕНИЯ", "ДАТА_ИСПОЛНЕНИЯ", "ДАТА_ПОЛУЧЕНИЯ_ОТЗЫВА", "КОД", "ССЫЛКА_ПОДТВЕРЖДЕНИЯ", "ССЫЛКА_ОТПИСКИ",
    "ИМЯ_ПРИГЛАСИВШЕГО", "КОНТАКТ", "ТЕКСТ_ПРЕДЛОЖЕНИЯ", "ДАТА_СПИСАНИЯ", "ОПЕРАЦИЯ", "КОНТАКТ_ПРЕДСТАВИТЕЛЯ",
    "ПОЛЕ", "ОБЪЯСНЕНИЕ", "ССЫЛКА_НА_НОРМУ_ФЗ",
))
# digits may be grouped with spaces, no-break spaces or hyphens: "7707 083893", "0098-7654-37"
_NUMBER = r"(\d(?:[\d \u00a0\u202f-]*\d)?)"
# between a label and its number: punctuation, a table bar, emphasis marks, a dash, tags and &nbsp;
# ("| ИНН | 7707083893 |", "ИНН: **7707083893**", "<td>ИНН</td><td>7707083893</td>", "ИНН — 7707083893")
_SEP = r"(?:<[^>]+>|&nbsp;|[\s:№#.,|*_\u00a0\u2014\u2013-])*"
# the Latin labels of a translation only in capitals: "Holiday Inn 2024" is not a requisite
_INN_LABEL = r"(?:(?i:ИНН)|INN)(?!\w)"
_OGRN_LABEL = r"(?:(?i:ОГРН(?:ИП)?)|OGRN(?:IP)?)(?!\w)"
INN_RE = re.compile(r"(?<!\w)" + _INN_LABEL + r"(?:\s*/\s*(?i:КПП))?" + _SEP + _NUMBER + r"(?:\s*/\s*\d+)?")
OGRN_RE = re.compile(r"(?<!\w)" + _OGRN_LABEL + _SEP + _NUMBER)
# "ИНН/ОГРН 7707083893/1027700132195": the first number is the INN, the second the OGRN
PAIR_RE = re.compile(r"(?<!\w)" + _INN_LABEL + r"\s*/\s*" + _OGRN_LABEL + _SEP + _NUMBER + r"\s*/\s*" + _NUMBER)
INN_LENGTHS, OGRN_LENGTHS = (10, 12), (13, 15)
# the label a foreign company's drafts print instead of INN and OGRN (documents.md, Placeholders)
REG_NUMBER_RE = re.compile(r"(?<!\w)регистрационный номер(?!\w)", re.I)
GROUPING = re.compile(r"[ \u00a0\u202f-]")
LEGAL_FORM_RE = re.compile(
    r"^(?:общество с ограниченной ответственностью|индивидуальный предприниматель|публичное акционерное общество|"
    r"акционерное общество|ооо|пао|оао|зао|ао|ип|нко)\s+")
QUOTES = set("«»„“”\"'‘’`")
DASHES = set("—–‒−")
MIN_FRAGMENT = 8


def line_starts(text):
    return [0] + [m.end() for m in re.finditer("\n", text)]


def line_of(starts, offset):
    low, high = 0, len(starts)
    while low < high:
        mid = (low + high) // 2
        if starts[mid] <= offset:
            low = mid + 1
        else:
            high = mid
    return low


def fold(text):
    """Lower-case, no quotes, one kind of dash and space, runs of spaces collapsed; plus a char->line map."""
    chars, lines = [], []
    line, space = 1, True
    for char in text:
        current = line
        if char == "\n":
            line += 1
        if char in QUOTES:
            continue
        if char in DASHES:
            char = "-"
        char = "е" if char in "ёЁ" else char
        if char.isspace():
            if space:
                continue
            chars.append(" ")
            lines.append(current)
            space = True
            continue
        for piece in char.casefold():
            chars.append(piece)
            lines.append(current)
        space = False
    return "".join(chars), lines


def fold_plain(text):
    return fold(text)[0].strip(" .,;:!?")


def digits_issue(file, line, kind, value, label, expected, blocking):
    return {"file": file, "line": line, "kind": kind, "value": value, "blocking": blocking,
            "message": "%s %r: %s (expected %s)" % (label, value, "wrong length or check digit", expected)}


def split_number(raw, lengths):
    """The digits of one requisite out of a matched run of digit groups.

    A first group that already has a full length stands alone ("7707083893 2024 г." is an INN and a year);
    otherwise the groups are one number written with spaces ("0098 7654 37"), cut at the longest prefix of a
    full length when the whole run is too long."""
    groups = [group for group in GROUPING.split(raw) if group]
    if len(groups[0]) in lengths:
        return groups[0]
    whole = "".join(groups)
    if len(whole) in lengths:
        return whole
    best, prefix = None, ""
    for group in groups:
        prefix += group
        if len(prefix) in lengths:
            best = prefix
    if best:
        return best
    return whole if len(whole) <= max(lengths) else groups[0]


def find_numbers(text):
    """([(offset, inn)], [(offset, ogrn)]) in the order of the text."""
    inns, ogrns = [], []
    for match in PAIR_RE.finditer(text):
        inns.append((match.start(), split_number(match.group(1), INN_LENGTHS)))
        ogrns.append((match.start(2), split_number(match.group(2), OGRN_LENGTHS)))
    # a pair is read once: blank it out, keeping every offset, before the single labels are searched
    rest = PAIR_RE.sub(lambda match: " " * len(match.group(0)), text)
    inns.extend((match.start(), split_number(match.group(1), INN_LENGTHS)) for match in INN_RE.finditer(rest))
    ogrns.extend((match.start(), split_number(match.group(1), OGRN_LENGTHS)) for match in OGRN_RE.finditer(rest))
    return sorted(inns), sorted(ogrns)


def check_numbers(path, text, starts, owner, public=False):
    """INN/OGRN checksum and mismatch issues as (line, column, issue).

    A failed check digit blocks only on a public page: in a draft the number stays as the owner gave it."""
    found = []
    inns, ogrns = [], []
    foreign = owner is not None and owner.get("status") == "foreign"
    inn_hits, ogrn_hits = find_numbers(text)
    for offset, value in inn_hits:
        line = line_of(starts, offset)
        inns.append((line, offset, value))
        if not _kb.inn_valid(value):
            found.append((line, offset, digits_issue(path, line, "inn_checksum", value, "INN", "10 or 12 digits", public)))
    for offset, value in ogrn_hits:
        line = line_of(starts, offset)
        ogrns.append((line, offset, value))
        if foreign:
            found.append((line, offset, {
                "file": path, "line": line, "kind": "mismatch", "field": "ogrn", "value": value, "blocking": True,
                "message": "a foreign company has no OGRN/OGRNIP: print the country and registration number"}))
        elif not _kb.ogrn_valid(value):
            found.append((line, offset,
                          digits_issue(path, line, "ogrn_checksum", value, "OGRN/OGRNIP", "13 or 15 digits", public)))
    if owner is None:
        return found, inns, ogrns

    def mismatch(line, column, field, value, message):
        found.append((line, column, {"file": path, "line": line, "kind": "mismatch", "field": field,
                                     "value": value, "blocking": True, "message": message}))

    expected_inn = GROUPING.sub("", owner.get("inn") or "")
    for line, column, value in inns:
        if not _kb.inn_valid(value):
            continue
        if not expected_inn:
            mismatch(line, column, "inn", value, "the document has an INN but answers.json does not (not confirmed)")
        elif value != expected_inn:
            mismatch(line, column, "inn", value, "INN %s differs from the owner INN in answers.json" % value)
    expected_ogrn = GROUPING.sub("", owner.get("ogrn") or "")
    for line, column, value in ogrns:
        if foreign or not _kb.ogrn_valid(value):
            continue
        if owner.get("status") == "npd":
            mismatch(line, column, "ogrn", value, "a self-employed owner (npd) has no OGRN/OGRNIP")
        elif not expected_ogrn:
            mismatch(line, column, "ogrn", value, "the document has an OGRN but answers.json does not (not confirmed)")
        elif value != expected_ogrn:
            mismatch(line, column, "ogrn", value, "OGRN %s differs from the owner OGRN in answers.json" % value)
    regs = []
    if foreign:
        regs = [(line_of(starts, m.start()), m.start(), "") for m in REG_NUMBER_RE.finditer(text)]
        expected_reg = GROUPING.sub("", owner.get("reg_number") or "")
        if regs and expected_reg and expected_reg.casefold() not in GROUPING.sub("", text).casefold():
            line, column, _ = regs[0]
            mismatch(line, column, "reg_number", owner.get("reg_number"),
                     "the registration number from answers.json is not in the document")
    name = owner.get("name")
    if name and (inns or ogrns or regs):
        core = LEGAL_FORM_RE.sub("", fold_plain(name))
        if core and core not in fold(text)[0]:
            line, column, _ = min(inns + ogrns + regs)
            mismatch(line, column, "name", name, "the owner name from answers.json is not in the document")
    return found, inns, ogrns


def is_offer(path, text, kind):
    if kind != "auto":
        return kind == "offer"
    if re.search(r"oferta|offer|оферт", os.path.basename(path), re.I):
        return True
    for line in text.splitlines():
        if line.strip():
            return bool(re.search(r"оферт|\boffer\b", line, re.I))
    return False


def fragments(pattern_text):
    quoted = re.findall(r"«([^»]+)»", pattern_text)
    return [fold_plain(item) for item in (quoted or [pattern_text]) if len(fold_plain(item)) >= MIN_FRAGMENT]


def check_clauses(path, text, clauses):
    folded, lines = fold(text)
    found = []
    for clause in clauses:
        for fragment in fragments(clause["pattern_text"]):
            start = folded.find(fragment)
            hits = 0
            while start != -1 and hits < 5:
                line = lines[start]
                original = next((q for q in re.findall(r"«([^»]+)»", clause["pattern_text"])
                                 if fold_plain(q) == fragment), clause["pattern_text"])
                severity = clause.get("severity", "violation")
                found.append((line, start, {
                    "file": path, "line": line, "kind": "forbidden_clause",
                    "severity": severity, "fragment": original.strip(" .,;:!?"),
                    "violates": clause.get("violates", ""), "blocking": severity != "risk",
                    "message": "clause from the forbidden list (%s)" % severity}))
                hits += 1
                start = folded.find(fragment, start + len(fragment))
    return found


def placeholder_kind(name):
    if name in REQUISITE_PLACEHOLDERS:
        return "placeholder_requisite"
    if name in RUNTIME_PLACEHOLDERS:
        return "placeholder_runtime"
    return "placeholder_fact"


def placeholder_issue(path, line, match, public, withheld):
    name = match.group(1)
    kind = placeholder_kind(name)
    if not public:
        blocking, message = False, "placeholder in a draft: fill it from answers.json or leave it for the owner"
    elif kind == "placeholder_requisite" and name in withheld:
        blocking, message = False, "requisite the owner withheld (owner.withheld): stays visible on the page"
    elif kind == "placeholder_runtime":
        blocking, message = True, ("per-user value on a public page: convert it to the project's interpolation "
                                   "({name}, ${name}, a template variable bound to the real data)")
    else:
        blocking, message = True, "unresolved placeholder on a public page: fill it or keep the page in the drafts"
    return {"file": path, "line": line, "kind": kind, "name": name, "text": match.group(0)[:100],
            "blocking": blocking, "message": message}


def check_file(path, owner, clauses, kind, public=False, withheld=()):
    text, encoding = _kb.read_text_enc(path)
    starts = line_starts(text)
    found = []
    if encoding != "utf-8":
        found.append((1, -1, {"file": path, "line": 1, "kind": "encoding", "encoding": encoding, "blocking": False,
                              "message": "the file is not UTF-8 and was read as %s" % encoding}))
    for match in PLACEHOLDER_RE.finditer(text):
        line = line_of(starts, match.start())
        found.append((line, match.start(), placeholder_issue(path, line, match, public, withheld)))
    for match in CONDITION_RE.finditer(text):
        if not CYRILLIC_RE.search(match.group(0)):
            continue  # "[1:]" in code is a slice, not a template marker
        line = line_of(starts, match.start())
        found.append((line, match.start(), {"file": path, "line": line, "kind": "condition",
                                            "text": match.group(0)[:100], "blocking": True}))
    numbers, _, _ = check_numbers(path, text, starts, owner, public)
    found.extend(numbers)
    if is_offer(path, text, kind):
        found.extend(check_clauses(path, text, [c for c in clauses if re.search(r"oferta|offer", c.get("template", ""))]))
    found.sort(key=lambda item: (item[0], item[1]))
    return [issue for _, _, issue in found]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="check_docs.py",
        description="Check drafted documents and public pages: leftover placeholders and condition markers, "
                    "INN/OGRN checksums (blocking on public pages), mismatches with answers.json, forbidden offer "
                    "clauses. Prints JSON; exits 1 only on blocking issues.",
        epilog="List the drafts before the options and give --public once per file, for example: check_docs.py "
               ".legal/drafts/*.md --public legal/privacy.html --public components/Footer.tsx "
               "--answers .legal/answers.json")
    parser.add_argument("files", nargs="*",
                        help="drafts for the owner (.legal/drafts/*.md), listed before the options; placeholders "
                             "never block in them")
    parser.add_argument("--public", action="append", default=[], metavar="FILE",
                        help="one public page or project file that renders legal text; repeat the flag once per file. "
                             "Every placeholder blocks there except requisites listed in answers.json owner.withheld")
    parser.add_argument("--answers", help=".legal/answers.json")
    parser.add_argument("--kb", default=_kb.DEFAULT_KB, help="jurisdiction pack directory (default: bundled ru)")
    parser.add_argument("--kind", choices=("auto", "offer", "other"), default="auto",
                        help="treat every file as an offer / not an offer (default: detect by name and heading)")
    return parser


def main(argv=None):
    args, code = _kb.parse_args(build_parser(), sys.argv[1:] if argv is None else argv)
    if args is None:
        return code
    public = list(dict.fromkeys(args.public))
    files = [path for path in dict.fromkeys(args.files) if path not in public] + public
    if not files:
        return _kb.fail("no files to check: pass drafts and/or --public pages")
    try:
        owner = _kb.answers_sections(_kb.load_answers(args.answers), args.answers)[0] if args.answers else None
        withheld = set((owner or {}).get("withheld") or ())
        clauses = _kb.load_forbidden_clauses(args.kb)
        issues = []
        for path in files:
            issues.extend(check_file(path, owner, clauses, args.kind, path in public, withheld))
    except _kb.KbError as exc:
        return _kb.fail(str(exc))
    summary = {}
    for issue in issues:
        summary[issue["kind"]] = summary.get(issue["kind"], 0) + 1
    blocking = sum(1 for issue in issues if issue["blocking"])
    _kb.emit({"files": files, "public": public, "issues": issues, "summary": summary, "blocking": blocking})
    return 1 if blocking else 0


if __name__ == "__main__":
    _kb.setup_stdio()
    sys.exit(main())
