"""Neutral wording for process markers of the private knowledge base.

Cards mention how the research was organised: phase codes («P27»), discovery notes, research
paths, hubs, the wiki itself. None of that means anything to a reader of the public pack. The
table below rewrites each recurring phrase; it is explicit on purpose, and every rule changes
only the process marker, never a statement of law. The word «raw» stays: the jurisdiction
README explains it.
"""

from __future__ import annotations

import re

_CODE = r"P\d{1,2}(?:[–-]P?\d{1,2})?"
_DISCOVERY_FORMS = {
    # preposition (lower case) -> form of «предварительный поиск»
    "в": "предварительном поиске", "на": "предварительном поиске", "при": "предварительном поиске",
    "из": "предварительного поиска", "от": "предварительного поиска", "для": "предварительного поиска",
    "источник": "предварительного поиска", "источники": "предварительного поиска",
    "источников": "предварительного поиска", "по": "предварительному поиску",
    "с": "предварительным поиском",
}
_NOTE_FORMS = {"а": "заметка", "е": "заметке", "и": "заметки", "у": "заметку"}


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _starts_sentence(match) -> bool:
    before = match.string[: match.start()]
    core = before.rstrip(" \t*")
    return (
        not core
        or core.endswith((".", "!", "?", ":", "\n"))
        or re.search(r"(?:^|\n)\s*[-*]\s*(?:\*\*)?$", before) is not None
    )


def _discovery(match) -> str:
    prep, note = match.group("prep"), match.group("note")
    if note:
        form = f"{_NOTE_FORMS.get(note, 'заметка')} предварительного поиска"
    else:
        form = _DISCOVERY_FORMS.get((prep or "").strip().lower(), "предварительный поиск")
    if not prep and match.group("word") == "D" and _starts_sentence(match):
        form = _capitalize(form)
    return (prep or "") + form


def _hub(match) -> str:
    return {"": "направление", "а": "направления", "е": "направлении", "у": "направлению", "ом": "направлением"}[
        match.group(1) or ""
    ]


# Order matters: earlier rules see the text first. Each entry is (name, pattern, replacement).
RULES = [
    # raw P22, raw КоАП P12, raw пути P16 -> raw
    ("raw-code", re.compile(rf"\b(raw(?: (?:КоАП|ГПК|ЗоЗПП))?) (?:пути )?{_CODE}\b"), r"\1"),
    # discovery notes
    ("raw-and-discovery", re.compile(r"\braw и [Dd]iscovery\b"), "raw и в предварительном поиске"),
    ("discovery", re.compile(
        rf"(?P<prep>\b(?:[Вв]|[Нн]а|[Пп]ри|[Ии]з|[Оо]т|[Дд]ля|[Пп]о|[Сс]|[Ии]сточник(?:и|ов)?)\s+)?"
        rf"(?P<word>[Dd])iscovery(?:-заметк(?P<note>[а-я]))?(?: {_CODE})?(?![\w-])"), _discovery),
    # research paths
    ("path-report", re.compile(rf"Path report {_CODE}"), "Отчёт исследования"),
    ("path-in", re.compile(rf"\b([Вв]) пути {_CODE}"), r"\1 базе"),
    ("path-search", re.compile(rf"\b([Пп]оиск\w*) пути {_CODE}"), r"\1"),
    ("path-paren", re.compile(rf"\(путь {_CODE}: "), "("),
    ("path-noun", re.compile(rf"\b(отметк\w*|отчёт\w*) пути {_CODE}"), r"\1 исследования"),
    ("path-verb", re.compile(rf"\b([Пп])уть {_CODE} (не )?(искал|читал)\b"),
     lambda m: ("И" if m.group(1) == "П" else "и") + f"сследование {m.group(2) or ''}{m.group(3)[:-1]}ло"),
    ("path-rest", re.compile(rf"\b[Пп]ут[иь] {_CODE}"), "исследования"),
    # codes
    ("code-dash", re.compile(rf"\s+—\s+направление {_CODE}(?=[.])"), ""),
    ("code-mark", re.compile(rf"\bОтметка {_CODE}"), "Отметка исследования"),
    ("code-noun", re.compile(rf"\b(поиск\w*|проверка) {_CODE}"), r"\1"),
    ("code-semicolon", re.compile(rf";\s*{_CODE}, (\d{{4}}-\d{{2}}-\d{{2}})"), r", \1"),
    ("code-paren-date", re.compile(rf"\({_CODE}, (\d{{4}}-\d{{2}}-\d{{2}})\)"), r"(\1)"),
    ("code-paren", re.compile(rf"[ \t]*\({_CODE}\)"), ""),
    ("code-in", re.compile(rf"\b([Вв]) {_CODE}\b"), r"\1 базе"),
    ("code-rest", re.compile(rf"[ \t]+{_CODE}\b"), ""),
    # hubs of the knowledge base
    ("hub-of-direction", re.compile(r"\bхаб направления\b"), "направление"),
    ("hub", re.compile(r"\bхаб(а|е|у|ом)?\b"), _hub),
    # the knowledge base itself
    ("wiki-subject", re.compile(r"\bwiki (не проверяла)\b"), r"база \1"),
    ("wiki-in", re.compile(r"\b([Вв]) wiki\b"), r"\1 базе"),
    ("wiki", re.compile(r"(?<![A-Za-z])wiki(?![A-Za-z])"), "базы"),
    ("schema-by", re.compile(r"\b([Пп]о) schema\.md"), r"\1 руководству базы"),
    ("schema", re.compile(r"schema\.md"), "руководство базы"),
    ("ingest", re.compile(r"при следующем ingest\b"), "при следующем обновлении базы"),
    ("sibling-topic", re.compile(r"в теме `modern-web-app-development`"), "в смежной теме вне базы"),
]


def scrub(text: str) -> str:
    """Apply the replacement table to ``text``."""
    for _, pattern, replacement in RULES:
        text = pattern.sub(replacement, text)
    return text
