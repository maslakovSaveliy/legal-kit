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
  inn_checksum           INN next to "ИНН" (or under an "ИНН" header cell) with a wrong length or check digit
  ogrn_checksum          OGRN/OGRNIP next to "ОГРН"/"ОГРНИП" (or under such a header cell), wrong length or check digit
  mismatch               INN, OGRN or owner name differs from answers.json (or is not confirmed there); a table with
                         a header row is compared only when it has one value row (more rows list recipients)
  forbidden_clause       an offer contains a clause from forbidden-clauses.json (severity violation|risk)
  encoding               the file is not clean UTF-8: read as cp1251 or utf-16, or as UTF-8 with invalid bytes replaced

Blocking: placeholders and failed check digits never block in drafts; in a public file a failed check digit blocks,
and so does every placeholder except a requisite listed in answers.json owner.withheld (a runtime one must become
the project's own interpolation). A forbidden clause blocks with severity violation, not with risk. `encoding`
never blocks. Every other kind blocks.

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
# "ИНН — 10 цифр" describes the number, it is not one
_NUMBER = r"(\d(?:[\d \u00a0\u202f-]*\d)?)(?!\d)(?![ \t\u00a0]*(?:цифр|знак|символ|digit))"
# between a label and its number: punctuation, a table bar, emphasis marks, a dash, tags and &nbsp;
# ("| ИНН | 7707083893 |", "ИНН: **7707083893**", "<td>ИНН</td><td>7707083893</td>", "ИНН — 7707083893")
# The gap stays inside one block: it does not cross a blank line, a table rule row (|---|), a table row or section tag
# in any case (<tr>, </TR>, <tbody>, </table>) or a dash that ends its line ("ИНН: —"), so a header cell never borrows
# a number of the next row.
_SEP = (r"(?:<(?!/?(?i:tr|thead|tbody|tfoot|table)\b)[^>\n]{1,200}>|&nbsp;|&\#160;|[ \t\r\u00a0:№#.,|*_]|-(?!--)"
        r"|[\u2014\u2013](?![ \t\r]*\n)|\n(?![ \t\r]*\n))*")
# the Latin labels of a translation only in capitals: "Holiday Inn 2024" is not a requisite
_INN_LABEL = r"(?:(?i:ИНН)|INN)(?!\w)"
_OGRN_LABEL = r"(?:(?i:ОГРН(?:ИП)?)|OGRN(?:IP)?)(?!\w)"
INN_RE = re.compile(r"(?<!\w)" + _INN_LABEL + r"(?:\s*/\s*(?i:КПП))?" + _SEP + _NUMBER + r"(?:\s*/\s*\d+)?")
OGRN_RE = re.compile(r"(?<!\w)" + _OGRN_LABEL + _SEP + _NUMBER)
# "ИНН/ОГРН 7707083893/1027700132195": the first number is the INN, the second the OGRN
PAIR_RE = re.compile(r"(?<!\w)" + _INN_LABEL + r"\s*/\s*" + _OGRN_LABEL + _SEP + _NUMBER + r"\s*/\s*" + _NUMBER)
INN_LENGTHS, OGRN_LENGTHS = (10, 12), (13, 15)
# Tables with a header row ("| ИНН | ОГРН |" over "|---|---|", or <tr><th>ИНН</th>…): the label is in the header,
# the numbers in the rows below, so the label pass above cannot reach them (table_numbers reads them by column).
CELL_INN = re.compile(r"(?i:ИНН)(?:\s*/\s*(?i:КПП))?|INN")
CELL_OGRN = re.compile(r"(?i:ОГРН(?:ИП)?)|OGRN(?:IP)?")
CELL_MARKUP = re.compile(r"<[^<>\n]{0,200}>|&nbsp;|&#160;")
CELL_LEAD = re.compile(r"(?:[ \t\r\n\u00a0*_]|<[^<>\n]{0,200}>|&nbsp;|&#160;)*")
CELL_NUMBER = re.compile(_NUMBER)
MD_RULE = re.compile(r"[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*")
MD_BAR = re.compile(r"(?<!\\)\|")
MAX_LABEL_CELL = 200
# markup read before a cell's number (tags of a nested table included); the bound keeps unclosed nested cells linear
MAX_CELL_LEAD = 1000
HTML_TABLE_TAG = re.compile(r"<(/?)(table|tr|th|td)\b[^<>]{0,500}>", re.I)
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


def _cell_label(text, start, end):
    """"inn" or "ogrn" when a header cell holds only a label ("ИНН", "**ОГРН**", "ИНН/КПП", "<b>INN</b>")."""
    if end - start > MAX_LABEL_CELL:
        return None
    label = CELL_MARKUP.sub("", text[start:end]).strip(" \t\r\n\u00a0*_`:")
    if CELL_INN.fullmatch(label):
        return "inn"
    if CELL_OGRN.fullmatch(label):
        return "ogrn"
    return None


def _cell_number(text, start, end):
    """(offset, digits) of a number that opens the cell text[start:end], after markup; None for "—" or empty."""
    lead = CELL_LEAD.match(text, start, min(end, start + MAX_CELL_LEAD))
    match = CELL_NUMBER.match(text, lead.end(), end)
    return (match.start(1), match.group(1)) if match else None


def _markdown_rows(text):
    """Tables of Markdown: lists of rows (row start, [(start, end) of each cell]), header row first."""
    tables, rows, previous = [], None, None
    position = 0
    for line in text.splitlines(True):
        start, position = position, position + len(line)
        body = line.rstrip("\r\n")
        bar = MD_BAR.search(body) is not None  # "a \\| b" has no bar: it is not a table row
        if rows is not None:
            if bar:
                rows.append((start, _md_cells(start, body)))
                continue
            tables.append(rows)
            rows = None
        if previous is not None and bar and MD_RULE.fullmatch(body):
            rows = [(previous[0], _md_cells(*previous))]
            previous = None
            continue
        previous = (start, body) if bar else None
    if rows is not None:
        tables.append(rows)
    return tables


def _md_cells(start, body):
    """Cell spans of one Markdown table row; the outer bars are optional, "\\|" is not a bar."""
    bars = [m.start() for m in MD_BAR.finditer(body)]
    edges = [-1] + bars + [len(body)]
    cells = [(start + a + 1, start + b) for a, b in zip(edges, edges[1:])]
    if not body[:bars[0]].strip():
        cells = cells[1:]
    if not body[bars[-1] + 1:].strip():
        cells = cells[:-1]
    return cells


def _html_rows(text):
    """Tables of HTML: lists of rows (row start, [(start, end) of each <th>/<td> cell]).

    One pass over the table tags, so an unclosed cell or row costs nothing extra: a cell ends at the next cell,
    row or table tag of its own table; a row ends at </tr>, the next <tr> or the table's end. A table opened inside
    a cell is read as a table of its own, and the outer cell goes on after its </table>, so a number in a nested
    table also belongs to the outer cell."""
    tables, stack = [], []
    rows, row, cell = [], None, None
    for match in HTML_TABLE_TAG.finditer(text):
        closing, name = match.group(1), match.group(2).lower()
        if name == "table" and not closing and cell is not None:
            stack.append((rows, row, cell))
            rows, row, cell = [], None, None
            continue
        if cell is not None:
            row[1].append((cell, match.start()))
            cell = None
        if name in ("th", "td"):
            if not closing:
                if row is None:
                    row = (match.start(), [])
                cell = match.end()
            continue
        if row is not None:
            rows.append(row)
            row = None
        if name == "tr" and not closing:
            row = (match.start(), [])
        elif name == "table":
            if rows:
                tables.append(rows)
            rows = []
            if closing and stack:
                rows, row, cell = stack.pop()
    while True:
        if cell is not None:
            row[1].append((cell, len(text)))
        if row is not None:
            rows.append(row)
        if rows:
            tables.append(rows)
        if not stack:
            return tables
        rows, row, cell = stack.pop()


def _add_table_hits(values, inns, ogrns, single, row_starts):
    """Add the numbers of one table's value rows; a table of exactly one value row marks them in single."""
    hits = [hit for row in values for hit in row]
    if len(values) == 1:
        single.update(hit[1] for hit in hits)
    for kind, offset, raw, row_start in hits:
        row_starts[offset] = row_start
        if kind == "inn":
            inns.append((offset, split_number(raw, INN_LENGTHS)))
        else:
            ogrns.append((offset, split_number(raw, OGRN_LENGTHS)))


def table_numbers(text):
    """([(offset, inn)], [(offset, ogrn)], single_row_offsets, row_starts) of tables with a header row.

    A header cell that holds only a label (ИНН, ИНН/КПП, ОГРН, ОГРНИП, INN, OGRN, OGRNIP) makes its column an INN
    or OGRN column; the number that opens each cell of that column in the rows below is read with split_number at
    its own offset. single_row_offsets holds the numbers of tables with exactly one value row: only those are the
    owner's requisites. A table of several rows lists recipients, so its numbers get a check digit test only.
    row_starts maps each number to where its row starts. A row is a header only when it has a label cell and no
    cell that opens with a number, so a key-value row (| ИНН | 7707083893 |, <th>ИНН</th><td>…</td>) stays with
    the label pass; a later header row starts a new table."""
    inns, ogrns, single, row_starts = [], [], set(), {}
    for rows in _markdown_rows(text) + _html_rows(text):
        header, values = None, []
        for row_start, cells in rows:
            labels = [_cell_label(text, a, b) for a, b in cells]
            if any(labels) and not any(_cell_number(text, a, b) for a, b in cells):
                if header is not None:
                    _add_table_hits(values, inns, ogrns, single, row_starts)
                header, values = labels, []
                continue
            if header is None:
                continue
            row = []
            for kind, (a, b) in zip(header, cells):
                number = _cell_number(text, a, b) if kind else None
                if number:
                    row.append((kind, number[0], number[1], row_start))
            values.append(row)
        if header is not None:
            _add_table_hits(values, inns, ogrns, single, row_starts)
    return inns, ogrns, single, row_starts


def find_numbers(text):
    """([(offset, inn)], [(offset, ogrn)], listed) in the order of the text.

    listed holds the offsets of numbers from a table of several value rows: they are checked for their check
    digit but not compared with answers.json. A number in a value cell of a header-row table is read once: by its
    label when the label is in the same row ("| ИНН | 7707083893 |"), otherwise by its column, so a label that
    reached it from another row never decides whether it is an INN or an OGRN."""
    table_inns, table_ogrns, single, row_starts = table_numbers(text)

    def from_another_row(label, number):
        return number in row_starts and label < row_starts[number]

    inns, ogrns = [], []
    seen = set()  # where each number read next to its label starts, so a table cell is not read twice
    for match in PAIR_RE.finditer(text):
        if from_another_row(match.start(), match.start(1)) or from_another_row(match.start(), match.start(2)):
            continue
        inns.append((match.start(), split_number(match.group(1), INN_LENGTHS)))
        ogrns.append((match.start(2), split_number(match.group(2), OGRN_LENGTHS)))
        seen.update((match.start(1), match.start(2)))
    # a pair is read once: blank it out, keeping every offset, before the single labels are searched
    rest = PAIR_RE.sub(lambda match: " " * len(match.group(0)), text)
    for pattern, lengths, hits in ((INN_RE, INN_LENGTHS, inns), (OGRN_RE, OGRN_LENGTHS, ogrns)):
        for match in pattern.finditer(rest):
            if from_another_row(match.start(), match.start(1)):
                continue
            hits.append((match.start(), split_number(match.group(1), lengths)))
            seen.add(match.start(1))
    listed = set()
    for table_hits, hits in ((table_inns, inns), (table_ogrns, ogrns)):
        for offset, value in table_hits:
            if offset in seen:
                continue
            seen.add(offset)
            hits.append((offset, value))
            if offset not in single:
                listed.add(offset)
    return sorted(inns), sorted(ogrns), listed


def check_numbers(path, text, starts, owner, public=False):
    """INN/OGRN checksum and mismatch issues as (line, column, issue).

    A failed check digit blocks only on a public page: in a draft the number stays as the owner gave it. Numbers of
    a table with several value rows (a list of recipients) get the check digit test only: they are not the owner's,
    so no mismatch, no name check and no foreign-owner OGRN rule."""
    found = []
    inns, ogrns = [], []
    foreign = owner is not None and owner.get("status") == "foreign"
    inn_hits, ogrn_hits, listed = find_numbers(text)
    for offset, value in inn_hits:
        line = line_of(starts, offset)
        if offset not in listed:
            inns.append((line, offset, value))
        if not _kb.inn_valid(value):
            found.append((line, offset, digits_issue(path, line, "inn_checksum", value, "INN", "10 or 12 digits", public)))
    for offset, value in ogrn_hits:
        line = line_of(starts, offset)
        if offset not in listed:
            ogrns.append((line, offset, value))
        if foreign and offset not in listed:
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
                              "message": ("the file has bytes that are not valid UTF-8; they were replaced"
                                          if encoding == "utf-8-damaged" else
                                          "the file is not UTF-8 and was read as %s" % encoding)}))
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
