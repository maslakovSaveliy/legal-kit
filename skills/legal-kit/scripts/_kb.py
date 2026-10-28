"""Shared helpers for the legal-kit scripts. Python 3.9+, standard library only.

Reads a jurisdiction pack (requirements.jsonl, elements.json, forbidden-clauses.json,
feature-map.json, BASE.md) and `.legal/answers.json`; holds the source allowlists and
the INN/OGRN checksum rules. Every script imports this module first: it also makes
sure the stdlib `select` module wins over the sibling select.py.
"""

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from urllib.parse import urlsplit


def _preload_stdlib_select():
    """scripts/select.py would shadow the stdlib `select` that socket/selectors import."""
    here = os.path.dirname(os.path.abspath(__file__))
    loaded = sys.modules.get("select")
    if loaded is not None:
        origin = getattr(loaded, "__file__", None) or ""
        if os.path.dirname(os.path.abspath(origin)) != here:
            return
        del sys.modules["select"]
    saved = list(sys.path)
    sys.path[:] = [p for p in saved if os.path.abspath(p or os.getcwd()) != here]
    try:
        import select  # noqa: F401
        import selectors  # noqa: F401
    finally:
        sys.path[:] = saved


_preload_stdlib_select()

ALLOWLIST = (
    "pravo.gov.ru", "publication.pravo.gov.ru", "ips.pravo.gov.ru", "*.gov.ru", "vsrf.ru", "ksrf.ru",
    "cbr.ru", "nalog.ru", "nalog.gov.ru", "sozd.duma.gov.ru", "regulation.gov.ru", "kremlin.ru",
)
PLATFORM_DOMAINS = ("developer.apple.com", "support.google.com", "rustore.ru", "developer.huawei.com",
                    "developer.android.com")

SUBJECTS = ("ul", "ip", "npd", "foreign")
MODELS = ("b2b", "b2c")
PRODUCTS = ("site", "webapp", "ios", "android", "bot")
DEFAULT_KB = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "references",
                          "jurisdictions", "ru")
DEFAULT_CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "references", "features",
                               "catalog.json")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A checkbox whose name, id or label matches is treated as a consent checkbox.
CONSENT_RE = re.compile(
    r"consent|agree|accept|terms|privacy|policy|pdn|personal|соглас|соглаш|персональн|политик|оферт|обработк|"
    r"принима[юе]|подтвержда|ознакомл|услови", re.I)


class KbError(Exception):
    """Bad or missing input; the scripts report it and exit with code 2."""


# --------------------------------------------------------------------------
# Output and CLI plumbing
# --------------------------------------------------------------------------

def setup_stdio():
    """UTF-8 on stdout/stderr even on consoles with a legacy code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def emit(obj):
    """Print a JSON document (UTF-8, stable key order of the dict as built)."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def fail(message):
    """Report bad input: JSON error on stdout, text on stderr; returns exit code 2."""
    sys.stderr.write(message + "\n")
    emit({"error": message})
    return 2


def parse_args(parser, argv):
    """argparse that returns (args, None) or (None, exit_code) instead of raising SystemExit."""
    try:
        return parser.parse_args(argv), None
    except SystemExit as exc:
        code = exc.code
        return None, (code if isinstance(code, int) else 2)


def csv_list(value):
    """'a, b,,c' -> ['a', 'b', 'c']; None stays None, '' becomes []."""
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError as exc:
        raise KbError("cannot read %s: %s" % (path, exc.strerror or exc))


def load_json(path):
    text = read_text(path)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise KbError("%s is not valid JSON: %s" % (path, exc))


def load_requirements(kb):
    """requirements.jsonl -> {id: record}, in file order."""
    path = os.path.join(str(kb), "requirements.jsonl")
    requirements = {}
    for number, line in enumerate(read_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise KbError("%s line %d is not valid JSON: %s" % (path, number, exc))
        if not isinstance(record, dict) or not record.get("id"):
            raise KbError("%s line %d has no id" % (path, number))
        requirements[record["id"]] = record
    return requirements


def load_elements(kb):
    """elements.json -> {'<template>:<id>': element}."""
    path = os.path.join(str(kb), "elements.json")
    data = load_json(path)
    if not isinstance(data, list):
        raise KbError("%s must hold a list" % path)
    return {"%s:%s" % (item.get("template"), item.get("id")): item for item in data if isinstance(item, dict)}


def load_forbidden_clauses(kb):
    path = os.path.join(str(kb), "forbidden-clauses.json")
    data = load_json(path)
    if not isinstance(data, list):
        raise KbError("%s must hold a list" % path)
    return [item for item in data if isinstance(item, dict) and item.get("pattern_text")]


def load_feature_map(kb):
    path = os.path.join(str(kb), "feature-map.json")
    data = load_json(path)
    if not isinstance(data, dict):
        raise KbError("%s must hold an object" % path)
    return data


def base_date(kb):
    """The 'Base date' line of BASE.md as YYYY-MM-DD, or None."""
    path = os.path.join(str(kb), "BASE.md")
    if not os.path.isfile(path):
        return None
    match = re.search(r"Base date:\s*(\d{4}-\d{2}-\d{2})", read_text(path))
    return match.group(1) if match else None


def load_answers(path):
    data = load_json(path)
    if not isinstance(data, dict):
        raise KbError("%s must hold an object" % path)
    return data


def answers_sections(answers, source="answers.json"):
    """(owner, audience, business, product) of answers.json, type-checked.

    Each section is an object or null (null -> empty). owner.status and audience.minors are strings or null,
    product.urls, product.kinds, business.sectors and owner.withheld are lists of strings or null. A wrong
    type raises KbError, so the scripts exit with a clear message instead of a traceback.
    """
    sections = []
    for name in ("owner", "audience", "business", "product"):
        value = answers.get(name)
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise KbError("%s: %r must be an object" % (source, name))
        sections.append(value)
    owner, audience, business, product = sections
    for section, key in ((owner, "status"), (audience, "minors"), (owner, "name"), (owner, "inn"), (owner, "ogrn")):
        if section.get(key) is not None and not isinstance(section[key], str):
            raise KbError("%s: %s must be a string or null" % (source, key))
    for section, key in ((product, "urls"), (product, "kinds"), (business, "sectors"), (owner, "withheld")):
        value = section.get(key)
        if value is not None and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            raise KbError("%s: %s must be a list of strings or null" % (source, key))
    return owner, audience, business, product


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

def parse_date(value):
    """'YYYY-MM-DD' -> date, anything else (None, 'mixed', other formats) -> None."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date(int(value[:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return None


def today_arg(value):
    """--today value -> date; None means the local date. Raises KbError on a bad value."""
    if value is None:
        return date.today()
    parsed = parse_date(value)
    if parsed is None:
        raise KbError("--today must be YYYY-MM-DD, got %r" % value)
    return parsed


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def requirement_dates(requirement):
    """Every ISO date of a requirement: norm_dates[].from and a non-'mixed' effective_from."""
    dates = {parse_date(item.get("from")) for item in requirement.get("norm_dates") or []
             if isinstance(item, dict)}
    dates.add(parse_date(requirement.get("effective_from")))
    dates.discard(None)
    return dates


def single_effective_date(requirement):
    """The requirement's own effective_from when it is one ISO date ('mixed' and null give None)."""
    return parse_date(requirement.get("effective_from"))


def latest_requirement_date(requirement):
    """Latest ISO date among norm_dates[].from and effective_from, or None."""
    dates = [parse_date(item.get("from")) for item in requirement.get("norm_dates") or []
             if isinstance(item, dict)]
    dates.append(parse_date(requirement.get("effective_from")))
    dates = [d for d in dates if d is not None]
    return max(dates) if dates else None


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

_HOST_RE = re.compile(r"^[a-z0-9.-]+$")


def url_host(url):
    """Lower-case ASCII host of an http(s) URL without port, or None.

    Strict on purpose: a browser reads `https://evil.test\\@pravo.gov.ru/` differently from urlsplit, so a URL
    with a backslash, a control character, whitespace, user info or a host outside [a-z0-9.-] is refused.
    """
    if not isinstance(url, str):
        return None
    url = url.strip()
    if "\\" in url or any(ord(char) < 0x21 or ord(char) == 0x7F for char in url):
        return None
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host or "@" in parts.netloc:
        return None
    try:
        host = host.lower().rstrip(".").encode("idna").decode("ascii")
    except UnicodeError:
        return None
    return host if _HOST_RE.match(host) else None


def _host_matches(host, patterns):
    for pattern in patterns:
        if pattern.startswith("*."):
            if host.endswith(pattern[1:]):
                return True
        elif host == pattern or host.endswith("." + pattern):
            return True
    return False


def is_allowlisted(url):
    host = url_host(url)
    return bool(host) and _host_matches(host, ALLOWLIST)


def is_platform_url(url):
    host = url_host(url)
    return bool(host) and _host_matches(host, PLATFORM_DOMAINS)


# --------------------------------------------------------------------------
# Catalog host rule
# --------------------------------------------------------------------------

_HOST_CANDIDATE = re.compile(
    r"(?<![\w.@-])(?:(?:https?:)?//)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?::\d{1,5})?"
    r"(/[^\s\"'<>\\)\]}`,;|]*)?", re.I)


class HostIndex:
    """Catalog `hosts` entries of the form host[/path-prefix].

    An observed URL matches an entry when its host equals the entry host or is a subdomain of it and,
    if the entry has a path prefix, the URL path starts with that prefix (a look-alike such as
    mc.yandex.ru.evil.test does not match mc.yandex.ru).
    """

    MAX_HOST_CHARS = 253
    MAX_HOST_LABELS = 127

    def __init__(self):
        self._by_host = {}
        self._longest = 1

    def add(self, owner, entry):
        host, _, path = str(entry).strip().lower().partition("/")
        host = host.strip(".")
        if host:
            self._by_host.setdefault(host, []).append((owner, "/" + path if path else ""))
            self._longest = max(self._longest, host.count(".") + 1)

    def __len__(self):
        return len(self._by_host)

    def lookup(self, host, path=""):
        """Owners whose entry matches the observed host and URL path."""
        host = host.lower().rstrip(".")
        if len(host) > self.MAX_HOST_CHARS:
            return []
        labels = host.split(".")
        if len(labels) > self.MAX_HOST_LABELS:
            return []
        path = (path or "").lower()
        owners = []
        # only the trailing labels can equal a catalog host: never more than the longest entry has
        for number in range(max(0, len(labels) - self._longest), len(labels)):
            for owner, prefix in self._by_host.get(".".join(labels[number:]), ()):
                if path.startswith(prefix) and owner not in owners:
                    owners.append(owner)
        return owners

    def find_in(self, text):
        """(offset, 'host/path', owner) for every host or URL in `text` that matches an entry."""
        if not self._by_host:
            return
        for match in _HOST_CANDIDATE.finditer(text):
            host, path = match.group(1), match.group(2) or ""
            for owner in self.lookup(host, path):
                yield match.start(1), host + path, owner


_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
MIN_NEEDLE = 3
MAX_NEEDLE = 40
_QUANTIFIER = re.compile(r"\{(\d*)(?:,(\d*))?\}")


class _Unsupported(Exception):
    """Regex syntax the needle extractor does not model; the pattern then runs ungated."""


class _Parser:
    """Parses the regex subset used by the catalog into a small tree.

    Nodes: ('lit', char), ('any',), ('zero',) for zero-width items, ('group', node), ('alt', [nodes]),
    ('seq', [nodes]), ('rep', node, minimum).
    """

    def __init__(self, pattern):
        self.text = pattern
        self.pos = 0

    def parse(self):
        node = self.alternation()
        if self.pos != len(self.text):
            raise _Unsupported("unbalanced")
        return node

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def alternation(self):
        branches = [self.sequence()]
        while self.peek() == "|":
            self.pos += 1
            branches.append(self.sequence())
        return branches[0] if len(branches) == 1 else ("alt", branches)

    def sequence(self):
        items = []
        while self.peek() not in ("", "|", ")"):
            items.append(self.quantified(self.atom()))
        return ("seq", items)

    def quantified(self, atom):
        while True:
            char = self.peek()
            if char in ("*", "+", "?"):
                self.pos += 1
                minimum = 1 if char == "+" else 0
            else:
                match = _QUANTIFIER.match(self.text, self.pos) if char == "{" else None
                if not match:
                    return atom
                self.pos = match.end()
                minimum = int(match.group(1) or 0)
            if self.peek() in ("?", "+"):  # lazy or possessive suffix
                self.pos += 1
            atom = ("rep", atom, minimum)

    def atom(self):
        char = self.text[self.pos]
        self.pos += 1
        if char == "(":
            return self.group()
        if char == "[":
            self.skip_class()
            return ("any",)
        if char == ".":
            return ("any",)
        if char in "^$":
            return ("zero",)
        if char == "\\":
            return self.escape()
        if char in "*+?{":
            raise _Unsupported("dangling quantifier")
        return ("lit", char)

    def escape(self):
        if self.pos >= len(self.text):
            raise _Unsupported("trailing backslash")
        char = self.text[self.pos]
        self.pos += 1
        if char in "bBAZ":
            return ("zero",)
        if char in "dDwWsS":
            return ("any",)
        if char in "nrtfv":
            return ("lit", {"n": "\n", "r": "\r", "t": "\t", "f": "\f", "v": "\v"}[char])
        if char.isalnum():
            raise _Unsupported("escape \\" + char)
        return ("lit", char)

    def skip_class(self):
        if self.peek() == "^":
            self.pos += 1
        if self.peek() == "]":
            self.pos += 1
        while self.pos < len(self.text) and self.text[self.pos] != "]":
            self.pos += 2 if self.text[self.pos] == "\\" else 1
        if self.pos >= len(self.text):
            raise _Unsupported("unterminated class")
        self.pos += 1

    def group(self):
        zero = False
        if self.text.startswith("?", self.pos):
            if self.text.startswith(("?:", "?=", "?!", "?<=", "?<!"), self.pos):
                zero = not self.text.startswith("?:", self.pos)
                self.pos += 3 if self.text.startswith(("?<=", "?<!"), self.pos) else 2
            elif self.text.startswith("?P<", self.pos):
                self.pos = self.text.index(">", self.pos) + 1
            elif self.text.startswith("?#", self.pos):
                self.pos = self.text.index(")", self.pos) + 1
                return ("zero",)
            else:
                flags = re.compile(r"\?([aiLmsux]+)([:)])").match(self.text, self.pos)
                if not flags:
                    raise _Unsupported("group construct")
                if "x" in flags.group(1):
                    raise _Unsupported("verbose mode")
                self.pos = flags.end()
                if flags.group(2) == ")":
                    return ("zero",)
        inner = self.alternation()
        if self.peek() != ")":
            raise _Unsupported("unbalanced group")
        self.pos += 1
        return ("zero",) if zero else ("group", inner)


def _required(node):
    """Lower-case literals of which at least one occurs in every match, or None when there is no such set."""
    kind = node[0]
    if kind == "lit":
        return {node[1].lower()}
    if kind in ("any", "zero"):
        return None
    if kind == "group":
        return _required(node[1])
    if kind == "rep":
        return _required(node[1]) if node[2] >= 1 else None
    if kind == "alt":
        sets = [_required(branch) for branch in node[1]]
        return None if any(item is None for item in sets) else set().union(*sets)
    candidates, run = [], []

    def flush():
        if run:
            candidates.append({"".join(run)})
            del run[:]

    for item in node[1]:
        if item[0] == "lit":
            run.append(item[1].lower())
        elif item[0] == "zero":
            continue  # a look-around or anchor consumes nothing: the literals around it stay adjacent
        elif item[0] == "rep" and item[1][0] == "lit" and item[2] >= 1:
            run.append(item[1][1].lower())
            flush()
        else:
            flush()
            inner = _required(item)
            if inner is not None:
                candidates.append(inner)
    flush()
    if not candidates:
        return None
    return max(candidates, key=lambda c: (min(len(w) for w in c), -len(c)))


def literal_needles(pattern):
    """Lower-case literals (3..40 chars) of which at least one occurs in every match of `pattern`, or None.

    Used to skip a regex on a file that contains none of them. None means "cannot tell": always run it.
    """
    try:
        needles = _required(_Parser(pattern).parse())
    except (_Unsupported, ValueError, IndexError):
        return None
    if not needles or any(len(word) < MIN_NEEDLE for word in needles):
        return None
    return frozenset(word[:MAX_NEEDLE] for word in needles)


def _trie_pattern(words):
    trie = {}
    for word in words:
        node = trie
        for char in word:
            node = node.setdefault(char, {})
        node[""] = True

    def render(node):
        parts = [re.escape(char) + render(child) for char, child in sorted(node.items()) if char]
        if not parts:
            return ""
        return "(?:" + "|".join(parts) + ")" + ("?" if "" in node else "")

    return render(trie)


class Feature:
    """One catalog entry with compiled patterns.

    deps: manifest dependency regexes. code and dom: (regex, is_keyword, needles) triples. Keyword patterns
    (sector.* features and any pattern with Cyrillic words) describe prose and run only on markup, UI and
    text files. `needles` are the literals that must occur in a file for the regex to be worth running.
    """

    def __init__(self, feature_id, deps, code, dom):
        self.id = feature_id
        self.deps = deps
        self.code = code
        self.dom = dom


class Catalog:
    """features/catalog.json: compiled patterns, one HostIndex over every `hosts` entry, one needle gate."""

    def __init__(self, entries, source="catalog"):
        self.warnings = []
        self.features = []
        self.hosts = HostIndex()
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id"):
                raise KbError("%s: every feature needs an id" % source)
            feature_id = entry["id"]
            deps = [re.compile(r"(?<![\w.@-])" + re.escape(dep) + r"(?![\w.-])", re.I)
                    for dep in entry.get("deps") or []]
            compiled = {"code": [], "dom": []}
            for kind in ("code", "dom"):
                for pattern in entry.get(kind) or []:
                    try:
                        regex = re.compile(pattern)
                    except re.error as exc:
                        self.warnings.append("catalog %s: skipped invalid %s regex %r (%s)"
                                             % (feature_id, kind, pattern, exc))
                        continue
                    keyword = feature_id.startswith("sector.") or bool(_CYRILLIC.search(pattern))
                    compiled[kind].append((regex, keyword, literal_needles(pattern)))
            for host in entry.get("hosts") or []:
                self.hosts.add(feature_id, host)
            self.features.append(Feature(feature_id, deps, compiled["code"], compiled["dom"]))
        words = sorted({w for f in self.features for _, _, needles in f.code + f.dom for w in needles or ()})
        self._closure = {w: tuple(w[:i] for i in range(MIN_NEEDLE, len(w) + 1) if w[:i] in set(words)) for w in words}
        self._gate = re.compile("(?=(" + _trie_pattern(words) + "))") if words else None

    def seen_needles(self, text):
        """Needles present in `text`, including those that are prefixes of a longer needle found there."""
        seen = set()
        if self._gate is not None:
            closure = self._closure
            for match in self._gate.finditer(text.lower()):
                seen.update(closure[match.group(1)])
        return seen

    def pattern_matches(self, text, code=True, dom=True, keyword=True, per_pattern=5, gate=True):
        """Yield (feature_id, offset, matched text) of code/dom patterns (at most `per_pattern` per regex).

        keyword=False skips keyword patterns; gate=False runs every regex whether or not its needles occur.
        """
        seen = self.seen_needles(text) if gate else None
        for feature in self.features:
            for enabled, patterns in ((code, feature.code), (dom, feature.dom)):
                if not enabled:
                    continue
                for regex, is_keyword, needles in patterns:
                    if (is_keyword and not keyword) or (seen is not None and needles and not needles & seen):
                        continue
                    for number, match in enumerate(regex.finditer(text)):
                        if number >= per_pattern:
                            break
                        yield feature.id, match.start(), match.group(0)


def load_catalog(path):
    data = load_json(path)
    if not isinstance(data, list):
        raise KbError("%s must hold a list of features" % path)
    return Catalog(data, str(path))


# --------------------------------------------------------------------------
# INN / OGRN checksums
# --------------------------------------------------------------------------

_INN10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_FIRST = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_SECOND = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _digits(value):
    return isinstance(value, str) and value.isascii() and value.isdigit()


def _inn_digit(digits, weights):
    return sum(int(d) * w for d, w in zip(digits, weights)) % 11 % 10


def inn_valid(value):
    """INN of 10 (legal entity) or 12 (individual) digits with a correct check digit."""
    if not _digits(value):
        return False
    if len(value) == 10:
        return _inn_digit(value, _INN10) == int(value[9])
    if len(value) == 12:
        return (_inn_digit(value, _INN12_FIRST) == int(value[10])
                and _inn_digit(value, _INN12_SECOND) == int(value[11]))
    return False


def ogrn_valid(value):
    """OGRN (13 digits) or OGRNIP (15 digits) with a correct check digit."""
    if not _digits(value):
        return False
    if len(value) == 13:
        return int(value[:12]) % 11 % 10 == int(value[12])
    if len(value) == 15:
        return int(value[:14]) % 13 % 10 == int(value[14])
    return False
