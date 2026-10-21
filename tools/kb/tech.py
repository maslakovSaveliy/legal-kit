"""Short, plain-text items from the bullet sections of a card.

``classify_tech`` also tells how firmly each item of «Техническое проявление» is anchored:
``norm`` (follows from the legal text), ``practice`` (engineering or market practice),
``interpretation`` (reading of the norm, position of an authority), ``inference`` or
``platform`` (rule of an app store). A qualifier in parentheses, a sentence-level qualifier or a
lead-in line over the list marks an item as non-norm; an unmarked item is a norm. The kind of
the card then caps it: only ``law`` and ``bylaw`` cards can yield ``norm``.
"""

from __future__ import annotations

import re

from .links import plain_text

_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")

# Bodies that publish positions, recommendations and letters but do not make law.
_ORGAN = (
    r"(?:органа|органов|РКН|ФНС|ФАС|ЦБ|ВС|Банка\s+России|Верховного\s+суда|ФТС"
    r"|Роспотребнадзор\w*|Роскомнадзор\w*|Росздравнадзор\w*|Минфин\w*|Минцифр\w*|Минздрав\w*"
    r"|Минэкономразвит\w*|Минпромторг\w*|Минюст\w*|Мин[а-яё]{4,})"
)
_LETTER_AUTHOR = (
    r"ФНС|Минфин\w*|РКН|ФАС|ЦБ|Банка\s+России|Минцифр\w*|Минздрав\w*|Роспотребнадзор\w*"
    r"|Минэкономразвит\w*|Минюст\w*|Минпромторг\w*"
)
_MARKERS = [
    ("practice", re.compile(r"инженерн\w*|(?<=\()практика\b|практик\w*\s+рынка|рыночн\w*\s+практик\w*", re.IGNORECASE)),
    ("interpretation", re.compile(
        r"трактовк\w*"
        rf"|(?i:позици[яиюей]|рекомендаци[яиюей])\s+{_ORGAN}"
        r"|(?i:по\s+рекомендаци\w*|рекомендаци\w*\s+для(?!\w))"
        r"|(?:ЦБ|РКН|ФАС|ФНС)\s+рекомендует"
        r"|(?<!\w)(?i:не)\s+(?i:требует)(?!ся)"
        # guidance of courts and regulators: reviews, plenums, FAQ, letters, court positions
        r"|(?<=\()(?:FAQ|ВС|Обзор\w*|Пленум\w*)(?!\w)"
        r"|Обзор\w*\s+(?:ВС|Верховного|\d{4})|Пленум\w*\s+(?:ВС\s+)?№|дел[аоуе]\s+ВС"
        r"|FAQ\s+(?:ФНС|ФАС|ЦБ|РКН|Минфин\w*)"
        r"|(?i:позици\w*\s+суд\w*)"
        rf"|(?i:письм\w*)\s+(?:{_LETTER_AUTHOR})"
    )),
    ("platform", re.compile(r"правил\w*\s+(?:магазин\w*|стор\w*)", re.IGNORECASE)),
]
_INFERENCE = re.compile(r"(?<!\w)вывод(?!\w)", re.IGNORECASE)
_NORM_LEAD = re.compile(r"прямо\s+(?:требуются|из\s+закона|следует)|требуются\s+законом", re.IGNORECASE)
_NEGATION = re.compile(r"(?<!\w)не(?!\w)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?;](?=\s|$)")
_LONG_SENTENCE = 120
_ABBREVIATIONS = {
    "ст", "ч", "п", "пп", "абз", "подп", "гл", "разд", "ред", "прил", "изм", "руб", "тыс", "млн", "млрд",
    "прим", "напр", "стр", "рис", "табл",
}

# What a norm becomes in cards that are not laws.
_DEMOTE = {"regulator": "interpretation", "court": "interpretation", "standard": "practice", "engineering": "practice"}


def gate_kind(kind: str, source_kind) -> str:
    """Cap the kind of a tech item by the ``source_kind`` of its card.

    ``store-policy`` cards give only ``platform``; ``regulator`` and ``court`` cards turn
    ``norm`` into ``interpretation``; ``standard`` and ``engineering`` cards turn it into
    ``practice``; any other card kind except ``law`` and ``bylaw`` gives ``interpretation``.
    ``source_kind=None`` means "do not cap".
    """
    if source_kind is None or source_kind in ("law", "bylaw"):
        return kind
    if source_kind == "store-policy":
        return "platform"
    if kind == "norm":
        return _DEMOTE.get(source_kind, "interpretation")
    return kind


def _sentence_ends(text: str) -> list:
    """End offsets (exclusive) of sentences, skipping abbreviation dots such as «ст.»."""
    ends = []
    for match in _SENTENCE_END.finditer(text):
        if match.group() != ";":
            word = re.search(r"(\w+)$", text[: match.start()])
            if word and word.group(1).isalpha() and (len(word.group(1)) <= 2 or word.group(1).lower() in _ABBREVIATIONS):
                continue
        ends.append(match.end())
    return ends


def _unmatched_openings(prefix: str) -> list:
    """Offsets of the opening parentheses that ``prefix`` leaves unclosed."""
    stack = []
    for index, char in enumerate(prefix):
        if char == "(":
            stack.append(index)
        elif char == ")" and stack:
            stack.pop()
    return stack


def _drop_dangling_abbreviation(window: str, minimum: int) -> str:
    """Drop abbreviations such as «ст.» or «в ред.» left at the end of a cut text."""
    while True:
        match = re.search(r"(?<!\w)(\w+)\.$", window)
        if not match or match.group(1).lower() not in _ABBREVIATIONS or match.start() < minimum:
            return window
        window = window[: match.start()].rstrip(" ,;:—-")


def _cut(text: str, limit: int, minimum: int = 0) -> str:
    """Shorten ``text`` to ``limit`` characters at a sentence end or a word, never before ``minimum``.

    The result never leaves a parenthesis open: a cut inside one goes back before it, or, if
    that would drop too much, closes it after the ellipsis.
    """
    if len(text) <= limit:
        return text.rstrip(" ,;:")
    ends = [
        end for end in _sentence_ends(text[: limit + 1])
        if minimum <= end <= limit and not _unmatched_openings(text[:end])
    ]
    if ends and (minimum or ends[-1] >= limit * 0.4):
        return text[: ends[-1]].rstrip()
    if minimum >= limit:
        return text[:limit]
    window = text[: limit - 1]
    space = window.rfind(" ")
    if space >= max(minimum, 1):
        window = window[:space]
    elif minimum:
        window = text[:minimum]
    window = _drop_dangling_abbreviation(window.rstrip(" ,;:—-"), minimum)
    floor = max(minimum, limit * 0.25)
    while True:
        openings = _unmatched_openings(window)
        if not openings:
            return window + "…"
        if openings[0] >= floor:
            window = window[: openings[0]].rstrip(" ,;:—-")
            continue
        room = text[: limit - 1 - len(openings)]
        space = room.rfind(" ")
        room = room[:space] if space >= 1 else room
        room = room.rstrip(" ,;:—-")
        return room + "…" + ")" * len(_unmatched_openings(room))


def compact(text: str, limit: int = 200, keep=None) -> str:
    """Collapse whitespace and shorten ``text`` to at most ``limit`` characters.

    The text is cut at the last sentence end when that keeps at least 40 % of the limit,
    otherwise at the last word followed by an ellipsis. ``keep`` is an optional ``(start, end)``
    span of the already collapsed text: the clause that holds the qualifier of the item. The cut
    never falls inside it; a clause that cannot follow the beginning within the limit is
    appended to a shortened beginning.
    """
    if keep is None:
        text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text.rstrip(" ,;:")
    if keep is None:
        return _cut(text, limit)
    start, end = keep
    if end <= limit:
        return _cut(text, limit, minimum=end)
    clause = text[start:end]
    room = limit - len(clause) - 2
    if room >= 30:
        return f"{_cut(text[:start].rstrip(), room + 1)} {clause}"
    return _cut(clause, limit)


def _clause_span(text: str, position: int):
    """Span of the parenthesis or the sentence that contains ``position`` (the qualifier clause)."""
    before = text[:position]
    if before.count("(") > before.count(")"):
        balance, start = 0, 0
        for index in range(position - 1, -1, -1):
            if text[index] == ")":
                balance += 1
            elif text[index] == "(":
                if balance == 0:
                    start = index
                    break
                balance -= 1
        depth, end = 1, len(text)
        for index in range(start + 1, len(text)):
            depth += (text[index] == "(") - (text[index] == ")")
            if depth == 0:
                end = index + 1
                break
        return start, end
    ends = [end for end in _sentence_ends(text) if not _unmatched_openings(text[:end])]
    start = max([end for end in ends if end <= position] or [0])
    end = min([end for end in ends if end > position] or [len(text)])
    start += len(text[start:]) - len(text[start:].lstrip())
    # In a very long sentence the clause starts at the qualifier itself.
    return (position if end - start > _LONG_SENTENCE else start), end


def _marker(text: str):
    """``(kind, start, end)`` of the earliest qualifier in ``text`` with its clause span, or None."""
    found = []
    for kind, pattern in _MARKERS:
        for match in pattern.finditer(text):
            found.append((match.start(), kind))
    for match in _INFERENCE.finditer(text):
        before = text[: match.start()]
        in_parentheses = before.count("(") > before.count(")")
        sentence_lead = re.search(r"(?:^|[.;:!?—]\s*)$", before) and re.match(r"\s*[:.,;—]", text[match.end():])
        stated = re.search(r"(?:^|\s)это\s*$", before)
        if in_parentheses or sentence_lead or stated:
            found.append((match.start(), "inference"))
    if not found:
        return None
    position, kind = min(found)
    return (kind, *_clause_span(text, position))


def _norm_lead(plain: str) -> bool:
    """True for a lead-in line that says the items below follow directly from the law."""
    for match in _NORM_LEAD.finditer(plain):
        left = re.split(r"[.;:]", plain[: match.start()])[-1]
        right = re.split(r"[.;:]", plain[match.end():])[0]
        if not _NEGATION.search(left) and not _NEGATION.search(right):
            return True
    return False


def _logical_items(section_md: str):
    """Split a section into list items and lead-in paragraphs.

    Returns ``(bullets, paragraphs)``. Every entry is ``(text, default_kind)`` where the default
    kind comes from the nearest lead-in line above the entry. Nested bullets and indented
    continuation lines are merged into their parent bullet; table rows are ignored.
    """
    lines = [line.rstrip() for line in section_md.split("\n") if line.strip() and not line.lstrip().startswith("|")]
    indents = [len(m.group(1).expandtabs(4)) for m in map(_BULLET.match, lines) if m]
    base = min(indents) if indents else 0

    bullets, paragraphs = [], []
    default = "norm"
    current = None  # [text, [children], default_kind]

    def flush():
        nonlocal current
        if current:
            text, children, kind = current
            if children:
                text = text.rstrip() + " " + "; ".join(child.rstrip(" .;,") for child in children)
            bullets.append((text, kind))
        current = None

    for line in lines:
        match = _BULLET.match(line)
        if match:
            nested = len(match.group(1).expandtabs(4)) > base
            if nested and current:
                current[1].append(match.group(2).strip())
            else:
                flush()
                current = [match.group(2).strip(), [], default]
        elif line[0].isspace() and current:
            if current[1]:
                current[1][-1] += " " + line.strip()
            else:
                current[0] += " " + line.strip()
        else:
            flush()
            text = line.strip()
            plain = plain_text(text)
            marker = _marker(plain)
            if marker:
                default = marker[0]
            elif _norm_lead(plain):
                default = "norm"
            paragraphs.append((text, default))
    flush()
    return bullets, paragraphs


def _item_text(plain: str, limit: int) -> str:
    marker = _marker(plain)
    return compact(plain, limit, keep=marker[1:] if marker else None)


def classify_tech(section_md: str, limit: int = 200, source_kind=None) -> list:
    """Return ``[{"kind", "text"}]`` for the items of «Техническое проявление в продукте».

    A section without bullets is read paragraph by paragraph. ``text`` is plain text of at
    most ``limit`` characters; the clause with the qualifier of an item is never cut. Pass the
    ``source_kind`` of the card to cap the kinds (see ``gate_kind``).
    """
    bullets, paragraphs = _logical_items(section_md)
    items = []
    for raw, default in bullets or paragraphs:
        plain = plain_text(raw)
        if len(plain) < 3:
            continue
        marker = _marker(plain)
        kind = gate_kind(marker[0] if marker else default, source_kind)
        items.append({"kind": kind, "text": _item_text(plain, limit)})
    return items


def cannot_check_items(section_md: str, limit: int = 200) -> list:
    """Return the items of «Что нельзя проверить по репозиторию» as plain text of at most ``limit`` characters."""
    bullets, paragraphs = _logical_items(section_md)
    texts = [_item_text(plain_text(raw), limit) for raw, _ in (bullets or paragraphs)]
    return [text for text in texts if len(text) >= 3]
