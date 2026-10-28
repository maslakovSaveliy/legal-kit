#!/usr/bin/env python3
"""Scan a source tree for legal-relevant signals. Python 3.9+, standard library only.

Reads the feature catalog (references/features/catalog.json) and the text files under ROOT.
Never writes. Prints JSON: stacks (ids of references/stacks/<id>.md) and frameworks, features
with evidence (file, line, match), legal pages, forms with consent-checkbox heuristics, design
inventory. The output is deterministic: sorted walk, sorted lists.

What is read: files up to 1 MB; node_modules, .git, build, dist, Pods, .dart_tool, secrets folders and
the skill's own .legal folder are skipped, so are generated or minified files, lock files, .env files and
keys. Catalog matching: `hosts` entries (host[/path-prefix]) match URLs and bare hosts found in source
(same host or a subdomain, and the path prefix); `deps` match package manifests; `code` regexes run on
source files; `dom` regexes and keyword patterns (sector.* features, Cyrillic words) run only on markup,
UI and text files (html, tsx, vue, php, templates, md; Flutter and SwiftUI/UIKit files). A regex whose
required literals do not occur in a file is skipped, which does not change the result.

Exit codes: 0 ok, 2 bad input.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _kb  # noqa: E402  (must come first: it protects the stdlib `select` module)

import argparse  # noqa: E402
import bisect  # noqa: E402
import html  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import stat  # noqa: E402

DEFAULT_CATALOG = _kb.DEFAULT_CATALOG

SKIP_DIRS = {
    "node_modules", ".git", "build", "dist", "Pods", ".dart_tool", ".venv", "venv", "__pycache__", ".next",
    "coverage", "vendor", ".legal", ".idea", ".vscode", ".gradle", ".expo", ".nuxt", ".svelte-kit", ".turbo",
    ".cache", ".tox", ".mypy_cache", ".pytest_cache", "DerivedData", ".superpowers",
    "secrets", ".secrets", ".ssh", ".aws", ".gnupg", ".kube",
}
DOC_DIRS = {"docs", "doc", "documentation"}
DOC_EXTS = {".md", ".mdx", ".rst", ".txt"}
# generated, minified or secret-bearing files are never read
SKIP_NAME_RE = re.compile(r"(\.(min|bundle|chunk)\.\w+$|\.map$|\.lock$|-lock\.\w+$|^\.env|"
                          r"\.(pem|key|p12|pfx|keystore|jks|p8|cer|crt|mobileprovision)$)", re.I)
MAX_FILE_BYTES = 1024 * 1024
MAX_EVIDENCE_PER_FEATURE = 30
MAX_EVIDENCE_PER_FILE = 5
MAX_FORM_CHARS = 6000
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb", "Podfile.lock",
             "poetry.lock", "Pipfile.lock", "composer.lock", "Gemfile.lock", "pubspec.lock", "Package.resolved",
             "Cargo.lock", "go.sum"}
BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".bmp", ".pdf", ".zip", ".gz", ".tar",
               ".jar", ".aar", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov", ".webm", ".so",
               ".dylib", ".a", ".o", ".class", ".dex", ".apk", ".ipa", ".map", ".lock", ".docx", ".xlsx", ".psd"}
# Markup, UI and text files: the only ones that get dom and keyword patterns (.dart and .swift only when
# they hold Flutter widgets or SwiftUI/UIKit views).
UI_TEXT_EXTS = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".astro", ".php", ".twig", ".njk", ".liquid",
                ".hbs", ".ejs", ".erb", ".jinja", ".j2", ".cshtml", ".razor", ".pug", ".md", ".mdx", ".dart",
                ".swift"}
SCAN_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro", ".html", ".htm", ".php",
             ".py", ".rb", ".java", ".kt", ".kts", ".swift", ".m", ".mm", ".h", ".dart", ".gradle", ".xml", ".plist",
             ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".twig", ".njk", ".liquid", ".hbs", ".ejs", ".erb",
             ".jinja", ".j2", ".pug", ".go", ".cs", ".cshtml", ".razor", ".scala", ".rs"}
MARKUP_EXTS = {".html", ".htm", ".php", ".tsx", ".jsx", ".js", ".vue", ".svelte", ".astro", ".twig", ".njk",
               ".liquid", ".hbs", ".ejs", ".erb", ".jinja", ".j2", ".cshtml", ".razor", ".pug"}
MANIFEST_NAMES = {"package.json", "pyproject.toml", "Pipfile", "pubspec.yaml", "Podfile", "Package.swift",
                  "build.gradle", "build.gradle.kts", "composer.json"}

# --------------------------------------------------------------------------
# Walking and reading
# --------------------------------------------------------------------------


def is_manifest(name):
    return name in MANIFEST_NAMES or bool(re.match(r"^requirements.*\.txt$", name))


def walk(root):
    """All files below root (skipping noise directories and symlinks) as (rel, abs, size), sorted."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            try:
                info = os.lstat(full)
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):  # symlinks, FIFOs, sockets and devices are never opened
                continue
            size = info.st_size
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            found.append((rel, full, size))
    found.sort(key=lambda item: item[0])
    return found


def read_text(path):
    """File text, or None for binary content."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


class LineIndex:
    def __init__(self, text):
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line(self, offset):
        return bisect.bisect_right(self.starts, offset)


def short(text, limit=120):
    return re.sub(r"\s+", " ", text).strip()[:limit]


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------

def scan_features(catalog, rel, text, flags, index, evidence, gate=True):
    """Collect evidence for every catalog feature in one file.

    flags: manifest (dependencies), code (source and config: code patterns, hosts), ui (markup, UI and
    text files: dom patterns and keyword patterns).
    """
    in_file = {}

    def add(feature_id, offset, matched):
        bucket = evidence.setdefault(feature_id, [])
        if in_file.get(feature_id, 0) >= MAX_EVIDENCE_PER_FILE or len(bucket) >= MAX_EVIDENCE_PER_FEATURE:
            return
        item = {"file": rel, "line": index.line(offset), "match": short(matched)}
        if item not in bucket:
            bucket.append(item)
            in_file[feature_id] = in_file.get(feature_id, 0) + 1

    if flags["manifest"] or flags["code"] or flags["ui"]:
        for offset, matched, feature_id in catalog.hosts.find_in(text):
            add(feature_id, offset, matched)
    if flags["manifest"]:
        for feature in catalog.features:
            for regex in feature.deps:
                for match in regex.finditer(text):
                    add(feature.id, match.start(), match.group(0))
    if flags["code"] or flags["ui"]:
        for feature_id, offset, matched in catalog.pattern_matches(
                text, code=True, dom=flags["ui"], keyword=flags["ui"], per_pattern=MAX_EVIDENCE_PER_FILE, gate=gate):
            add(feature_id, offset, matched)


# --------------------------------------------------------------------------
# Tokens and legal pages
# --------------------------------------------------------------------------

def tokens(path):
    """Lower-case words of a path, camelCase and punctuation split."""
    words = []
    for part in re.split(r"[^A-Za-z0-9]+", path):
        for piece in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", part):
            words.append(piece.lower())
    return words


LEGAL_KINDS = (
    ("cookie", {"cookie", "cookies"}),
    ("privacy", {"privacy", "policy", "politika"}),
    ("offer", {"oferta", "offer"}),
    ("terms", {"terms", "soglashenie", "agreement"}),
    ("consent", {"soglasie"}),
    ("refund", {"vozvrat", "refund", "returns"}),
    ("requisites", {"rekvizity", "requisites"}),
    ("contacts", {"contacts"}),
)
LEGAL_PAGE_EXTS = {".html", ".htm", ".md", ".mdx", ".php", ".twig", ".njk", ".liquid", ".hbs", ".ejs", ".pug",
                   ".tsx", ".jsx", ".vue", ".svelte", ".astro", ".dart", ".swift", ".kt", ".pdf", ".docx", ".txt",
                   ".jinja", ".j2"}
NON_PAGE_WORDS = {"test", "tests", "spec", "stories", "story", "mock", "mocks", "fixture", "fixtures", "snapshots"}
PAGE_STEMS = {"page", "index"}
HEADING_KINDS = (
    ("cookie", re.compile(r"cookie|куки", re.I)),
    ("privacy", re.compile(r"конфиденциальн|обработк\w+ персональн|privacy", re.I)),
    ("offer", re.compile(r"оферт|public offer", re.I)),
    ("terms", re.compile(r"пользовательск\w+ соглашени|terms of|условия использования", re.I)),
    ("refund", re.compile(r"возврат|refund|return policy", re.I)),
    ("requisites", re.compile(r"реквизит|requisites", re.I)),
    ("contacts", re.compile(r"контакт", re.I)),
)


def legal_kind_by_path(rel):
    base = rel.rsplit("/", 1)[-1]
    stem, ext = os.path.splitext(base)
    if ext.lower() not in LEGAL_PAGE_EXTS:
        return None
    words = tokens(rel)
    if NON_PAGE_WORDS & set(words):
        return None
    stem_words = set(tokens(stem))
    parent_words = set(tokens(rel.rsplit("/", 1)[0])) if "/" in rel else set()
    pool = stem_words | (parent_words if stem_words and stem_words <= PAGE_STEMS else set())
    for kind, keywords in LEGAL_KINDS:
        if pool & keywords:
            return kind
    return None


def legal_kind_by_heading(rel, text):
    if os.path.splitext(rel)[1].lower() not in LEGAL_PAGE_EXTS or not text:
        return None
    head = text[:4096]
    match = (re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
             or re.search(r"<h1[^>]*>(.*?)</h1>", head, re.I | re.S)
             or re.search(r"^#\s+(.+)$", head, re.M))
    if not match:
        return None
    title = strip_tags(match.group(1))
    for kind, regex in HEADING_KINDS:
        if regex.search(title):
            return kind
    return None


# --------------------------------------------------------------------------
# Forms
# --------------------------------------------------------------------------

CONSENT_RE = _kb.CONSENT_RE
_ATTRS = r"""(?:[^>"'{}]|"[^"]*"|'[^']*'|\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})*"""
FORM_OPEN = re.compile(r"<(?:[a-z]+-)?form(?=[\s>/])", re.I)
FORM_CLOSE = re.compile(r"</(?:[a-z]+-)?form\s*>", re.I)
INPUT_TAG = re.compile(r"<input\b" + _ATTRS + ">", re.I)
TEXTAREA_TAG = re.compile(r"<(?:textarea|select)\b" + _ATTRS + ">", re.I)
FIELD_COMPONENT = re.compile(
    r"<(?:TextField|Input|Textarea|TextArea|PasswordInput|PhoneInput|InputNumber|NumberInput|Select|NativeSelect|"
    r"DatePicker|FormField|Field|TextInput|v-text-field|el-input|a-input|q-input)\b" + _ATTRS + ">")
CHECKBOX_COMPONENT = re.compile(
    r"<(?:Checkbox|CheckBox|CheckboxField|v-checkbox|el-checkbox|a-checkbox|q-checkbox|mat-checkbox|b-form-checkbox|"
    r"BouncyCheckbox)\b" + _ATTRS + ">")
CHECKED_ATTR = re.compile(
    r"""(?<![\w.-])(?::|v-bind:)?(?:is)?(?:[Dd]efault)?[Cc]hecked(?:\s*=\s*("[^"]*"|'[^']*'|\{(?:[^{}]|\{[^{}]*\})*\}))?""")
REGISTER = re.compile(r"""register\(\s*['"]([^'"]+)['"]""")
SKIPPED_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}


def strip_tags(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", text))).strip()


def attr(tag, *names):
    for name in names:
        match = re.search(r"(?<![\w-])" + re.escape(name) + r"""\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*["'`]([^"'`]*)["'`]\s*\})""",
                          tag)
        if match:
            return next(group for group in match.groups() if group is not None)
    return None


def field_name(tag):
    registered = REGISTER.search(tag)
    return (attr(tag, "name") or (registered.group(1) if registered else None)
            or attr(tag, "formControlName", "v-model", "ng-model", "id", "label", "placeholder", "aria-label"))


def is_prechecked(tag):
    for match in CHECKED_ATTR.finditer(tag):
        value = match.group(1)
        if value is None:
            return True
        inner = value[1:-1].strip()
        if value[0] == "{":
            if inner == "true":
                return True
        elif inner.lower() in ("", "checked", "true"):
            return True
    return False


def checkbox_label(block, start, end, tag):
    parts = [attr(tag, name) for name in ("aria-label", "label", "title")]
    own_id = attr(tag, "id")
    if own_id:
        match = re.search(r"<label\b[^>]*\bfor\s*=\s*[\"']" + re.escape(own_id) + r"[\"'][^>]*>(.*?)</label>",
                          block, re.I | re.S)
        if match:
            parts.append(strip_tags(match.group(1)))
    label_open = block.rfind("<label", 0, start)
    if label_open > block.rfind("</label", 0, start):
        parts.append(strip_tags(block[label_open:start]))
    tail = block[end:end + 400]
    cut = re.search(r"<(?:input|textarea|select|button|Checkbox|CheckBox|TextField|Input|TextInput)\b|</?(?:[a-z]+-)?form\b",
                    tail, re.I)
    parts.append(strip_tags(tail[:cut.start()] if cut else tail))
    return short(" ".join(p for p in parts if p), 160)


def finish_form(file, line, fields, boxes):
    consent = any(box["consent"] for box in boxes)
    return {"file": file, "line": line, "fields": fields, "has_consent_checkbox": consent,
            "prechecked": any(box["consent"] and box["prechecked"] for box in boxes), "checkboxes": boxes}


def unique(values):
    seen, result = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def markup_forms(rel, text, index):
    forms = []
    for opener in FORM_OPEN.finditer(text):
        limit = opener.start() + MAX_FORM_CHARS
        closer = FORM_CLOSE.search(text, opener.end(), limit)
        if closer:
            end = closer.end()
        else:  # unclosed form: it ends where the next one starts, so unclosed forms do not pile up quadratically
            following = FORM_OPEN.search(text, opener.end(), limit)
            end = following.start() if following else min(len(text), limit)
        block = text[opener.start():end]
        found = []  # (offset, kind, tag)
        for match in INPUT_TAG.finditer(block):
            found.append((match.start(), "input", match.group(0)))
        for match in TEXTAREA_TAG.finditer(block):
            found.append((match.start(), "field", match.group(0)))
        for match in FIELD_COMPONENT.finditer(block):
            found.append((match.start(), "field", match.group(0)))
        for match in CHECKBOX_COMPONENT.finditer(block):
            found.append((match.start(), "checkbox", match.group(0)))
        found.sort()
        fields, boxes = [], []
        for offset, kind, tag in found:
            input_type = (attr(tag, "type") or "text").lower() if kind == "input" else ""
            if kind == "checkbox" or input_type == "checkbox":
                label = checkbox_label(block, offset, offset + len(tag), tag)
                name = field_name(tag) or ""
                boxes.append({"name": name, "label": label, "consent": bool(CONSENT_RE.search(name + " " + label)),
                              "prechecked": is_prechecked(tag)})
            elif input_type not in SKIPPED_INPUT_TYPES:
                fields.append(field_name(tag))
        forms.append(finish_form(rel, index.line(opener.start()), unique(fields), boxes))
    return forms


WIDGET_CONFIGS = {
    ".dart": {
        "form": re.compile(r"\bForm\s*\("),
        "fields": re.compile(r"\b(?:TextFormField|TextField|DropdownButtonFormField|FormBuilderTextField)\s*\("),
        "boxes": re.compile(r"\b(?:CheckboxListTile|Checkbox|FormBuilderCheckbox|SwitchListTile)\s*\("),
        "label": re.compile(r"""(?:labelText|hintText)\s*:\s*(?:const\s+)?['"]([^'"]+)['"]"""),
        "on": re.compile(r"\b(?:value|initialValue)\s*:\s*true\b"),
    },
    ".swift": {
        "form": re.compile(r"\bForm\s*\{"),
        "fields": re.compile(r"\b(?:TextField|SecureField|TextEditor)\s*\("),
        "boxes": re.compile(r"\bToggle\s*\("),
        "label": re.compile(r"""(?:TextField|SecureField)\s*\(\s*"([^"]+)\""""),
        "on": re.compile(r"isOn\s*:\s*\.constant\(\s*true\s*\)"),
    },
    ".kt": {
        "form": None,
        "fields": re.compile(r"\b(?:OutlinedTextField|TextField|BasicTextField)\s*\("),
        "boxes": re.compile(r"\b(?:Checkbox|Switch)\s*\("),
        "label": re.compile(r"""label\s*=\s*\{\s*Text\(\s*"([^"]+)\""""),
        "on": re.compile(r"checked\s*=\s*true\b"),
    },
    "react-native": {
        "form": None,
        "fields": re.compile(r"<TextInput\b"),
        "boxes": re.compile(r"<(?:Checkbox|CheckBox|BouncyCheckbox|Switch)\b"),
        "label": re.compile(r"""placeholder\s*=\s*\{?\s*["']([^"']+)["']"""),
        "on": re.compile(r"\b(?:value|isChecked|checked|isChecking)\s*=\s*\{\s*true\s*\}"),
    },
}


def widget_forms(rel, text, index, config):
    widgets = sorted([(m.start(), "field") for m in config["fields"].finditer(text)]
                     + [(m.start(), "box") for m in config["boxes"].finditer(text)])
    if not widgets:
        return []
    anchors = [m.start() for m in config["form"].finditer(text)] if config["form"] else []
    if anchors:
        groups = []
        for number, start in enumerate(anchors):
            end = min(anchors[number + 1] if number + 1 < len(anchors) else len(text), start + 8000)
            groups.append((start, end))
    else:
        groups = [(widgets[0][0], min(len(text), widgets[-1][0] + 600))]
    forms = []
    for start, end in groups:
        inside = [(pos, kind) for pos, kind in widgets if start <= pos < end]
        fields, boxes = [], []
        for number, (pos, kind) in enumerate(inside):
            limit = inside[number + 1][0] if number + 1 < len(inside) else end
            window = text[pos:min(limit, pos + 500)]
            if kind == "field":
                label = config["label"].search(window)
                fields.append(label.group(1) if label else "field")
            else:
                boxes.append({"name": "", "label": short(" ".join(re.findall(r"""['"]([^'"\n]{2,})['"]""", window)), 160),
                              "consent": bool(CONSENT_RE.search(window)), "prechecked": bool(config["on"].search(window))})
        if fields or any(box["consent"] for box in boxes):
            forms.append(finish_form(rel, index.line(start), fields, boxes))
    return forms


def forms_in(rel, text, index):
    ext = os.path.splitext(rel)[1].lower()
    forms = []
    if ext in MARKUP_EXTS:
        forms = markup_forms(rel, text, index)
        if not forms and ext in (".tsx", ".jsx", ".js") and "react-native" in text:
            forms = widget_forms(rel, text, index, WIDGET_CONFIGS["react-native"])
    elif ext in WIDGET_CONFIGS:
        forms = widget_forms(rel, text, index, WIDGET_CONFIGS[ext])
    return forms


# --------------------------------------------------------------------------
# Stacks and design inventory
# --------------------------------------------------------------------------

def npm_dependencies(text):
    try:
        data = json.loads(text)
    except ValueError:
        return set()
    names = set()
    if isinstance(data, dict):
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            if isinstance(data.get(section), dict):
                names.update(data[section])
    return names


BOT_NPM = ("telegraf", "grammy", "node-telegram-bot-api", "@maxhub/max-bot-api")
BOT_PY = re.compile(r"(?im)^\s*(?:aiogram|python-telegram-bot|pytelegrambotapi|maxapi)\b")


def detect_stacks(rels, npm, py_text, pubspec, composer):
    """-> (stacks, frameworks). `stacks` are ids of references/stacks/<id>.md; `frameworks` is finer detail."""
    stacks, frameworks = set(), set()
    base_names = {r.rsplit("/", 1)[-1] for r in rels}
    exts = [os.path.splitext(r)[1].lower() for r in rels]
    flutter = "pubspec.yaml" in base_names and bool(re.search(r"\bflutter\s*:", pubspec))
    native_js = "react-native" in npm or "expo" in npm
    if "next" in npm:
        stacks.add("nextjs")
    if native_js:
        stacks.add("react-native")
        frameworks.add("expo" if "expo" in npm else "react-native")
    if "react" in npm:
        frameworks.add("react")
        if "next" not in npm and not native_js:
            stacks.add("react")
    if any(n.startswith("@nestjs/") for n in npm):
        stacks.add("nestjs")
    if flutter:
        stacks.add("flutter")
    for package, framework in (("vue", "vue"), ("nuxt", "nuxt"), ("@sveltejs/kit", "sveltekit"),
                               ("@angular/core", "angular")):
        if package in npm:
            stacks.add("generic-web")
            frameworks.add(framework)
    if "astro" in npm:
        stacks.add("static-html")
        frameworks.add("astro")
    if not (flutter or native_js):
        has_xcode = any(".xcodeproj/" in r or ".xcworkspace/" in r for r in rels)
        if ".swift" in exts or "Package.swift" in base_names or has_xcode:
            stacks.add("swift")
        if "AndroidManifest.xml" in base_names and (".kt" in exts or ".java" in exts):
            frameworks.add("android")  # no stack file: reported as "verify manually"
    py_files = [n for n in base_names if re.match(r"^requirements.*\.txt$", n)] + [
        n for n in ("pyproject.toml", "Pipfile", "setup.py", "manage.py") if n in base_names]
    if py_files:
        stacks.add("python")
        for name in ("django", "flask", "fastapi"):
            if name in py_text or (name == "django" and "manage.py" in base_names):
                frameworks.add(name)
    wordpress = "wp-config.php" in base_names or any(r.startswith("wp-content/") for r in rels)
    bitrix = any(r.startswith(("bitrix/", "local/")) for r in rels)
    if wordpress or bitrix:
        stacks.add("no-code")
        frameworks.update(name for name, found in (("wordpress", wordpress), ("bitrix", bitrix)) if found)
    elif "composer.json" in base_names or exts.count(".php") > 3:
        stacks.add("generic-web")
        frameworks.add("laravel" if ("laravel/framework" in composer or "artisan" in base_names) else "php")
    if any(name in npm for name in BOT_NPM) or re.search(BOT_PY, py_text):
        stacks.add("bot")
    # a lone handler such as send.php next to plain pages is still a static site
    if ({".html", ".htm"} & set(exts)) and not stacks:
        stacks.add("static-html")
    return sorted(stacks), sorted(frameworks)


UI_LIB_DEPS = (
    ("radix", lambda n: any(x.startswith("@radix-ui/") for x in n)),
    ("mui", lambda n: "@mui/material" in n),
    ("chakra", lambda n: any(x.startswith("@chakra-ui/") for x in n)),
    ("antd", lambda n: "antd" in n),
    ("mantine", lambda n: "@mantine/core" in n),
    ("tailwind", lambda n: "tailwindcss" in n),
    ("bootstrap", lambda n: "bootstrap" in n or "react-bootstrap" in n),
    ("styled-components", lambda n: "styled-components" in n),
    ("emotion", lambda n: "@emotion/react" in n),
    ("react-native-paper", lambda n: "react-native-paper" in n),
    ("nativewind", lambda n: "nativewind" in n),
    ("tamagui", lambda n: "tamagui" in n),
    ("gluestack", lambda n: any(x.startswith("@gluestack-ui/") for x in n)),
    ("vuetify", lambda n: "vuetify" in n),
    ("primevue", lambda n: "primevue" in n),
    ("element-plus", lambda n: "element-plus" in n),
    ("quasar", lambda n: "quasar" in n),
    ("angular-material", lambda n: "@angular/material" in n),
)
I18N_DEPS = (
    ("next-intl", "next-intl"), ("next-i18next", "next-i18next"), ("react-i18next", "react-i18next"),
    ("i18next", "i18next"), ("react-intl", "react-intl"), ("lingui", "@lingui/core"), ("vue-i18n", "vue-i18n"),
    ("@nuxtjs/i18n", "@nuxtjs/i18n"), ("svelte-i18n", "svelte-i18n"), ("ngx-translate", "@ngx-translate/core"),
    ("nestjs-i18n", "nestjs-i18n"), ("i18n-js", "i18n-js"), ("expo-localization", "expo-localization"),
)
CATALOG_PATHS = (
    re.compile(r"(^|/)(messages|locales?|translations?|i18n|l10n|lang)/[^/]+\.(json|ya?ml|po|arb|xlf|xliff|php|properties)$"),
    re.compile(r"(^|/)(messages|locales?|translations?|i18n|l10n|lang)/[^/]+/[^/]+\.(json|ya?ml|po|php)$"),
    re.compile(r"\.arb$"),
    re.compile(r"(^|/)Localizable\.(xcstrings|strings)$"),
    re.compile(r"\.lproj/[^/]+\.strings$"),
    re.compile(r"(^|/)locale/[^/]+/LC_MESSAGES/[^/]+\.po$"),
    re.compile(r"(^|/)res/values[^/]*/strings\.xml$"),
)
TOKEN_FILE = re.compile(
    r"^(tailwind\.config\.\w+|theme\.\w+|tokens?\.\w+|design-tokens.*|_?variables\.(s?css|less)|colors\.\w+|"
    r"app_theme\.dart|palette\.\w+)$", re.I)
TOKEN_DIRS = {"theme", "themes", "tokens", "design-system"}
LAYOUT_NAMES = {"base.html", "base.html.twig", "base.twig", "_app.tsx", "_app.js", "_document.tsx", "_document.js",
                "App.vue", "app.vue", "header.php", "footer.php"}
ROUTE_FILES = (
    re.compile(r"(^|/)app/(.*/)?(page|route)\.(tsx|jsx|js|ts)$"), re.compile(r"(^|/)pages/[^_][^/]*\.(tsx|jsx|js|ts)$"),
    re.compile(r"(^|/)pages/.+/index\.(tsx|jsx|js|ts)$"), re.compile(r"(^|/)urls\.py$"),
    re.compile(r"(^|/)routes/web\.php$"), re.compile(r"(^|/)router\.dart$"), re.compile(r"\.controller\.ts$"),
    re.compile(r"(^|/)src/routes/.+/\+page\.svelte$"), re.compile(r"(^|/)(app|src/app)/routes\.(ts|tsx)$"),
)


def component_files(rels, word):
    result = []
    for rel in rels:
        ext = os.path.splitext(rel)[1].lower()
        if ext in (".tsx", ".jsx", ".vue", ".svelte", ".astro", ".dart", ".swift", ".kt", ".js", ".ts") \
                and word in tokens(os.path.splitext(rel.rsplit("/", 1)[-1])[0]):
            result.append(rel)
    return result


def design_inventory(rels, npm, pubspec, footer_markup):
    base_names = {r.rsplit("/", 1)[-1] for r in rels}
    ui_libs = [name for name, test in UI_LIB_DEPS if test(npm)]
    if "components.json" in base_names:
        ui_libs.append("shadcn")
    if any(re.match(r"^tailwind\.config\.\w+$", n) for n in base_names) and "tailwind" not in ui_libs:
        ui_libs.append("tailwind")
    if re.search(r"uses-material-design\s*:\s*true", pubspec):
        ui_libs.append("flutter-material")
    if "cupertino_icons" in pubspec:
        ui_libs.append("flutter-cupertino")

    tokens_found = [r for r in rels if TOKEN_FILE.match(r.rsplit("/", 1)[-1])
                    or (TOKEN_DIRS & set(r.lower().split("/")[:-1]) and os.path.splitext(r)[1] in SCAN_EXTS)]

    lib = next((name for name, dep in I18N_DEPS if dep in npm), None)
    if lib is None:
        for name in ("flutter_localizations", "easy_localization", "slang", "intl"):
            if re.search(r"(?m)^\s*%s\s*:" % name, pubspec):
                lib = name if name != "flutter_localizations" else "flutter_localizations"
                break
    catalogs = sorted(r for r in rels if any(p.search(r) for p in CATALOG_PATHS))
    if lib is None and catalogs:
        if any(r.endswith((".xcstrings", ".strings")) for r in catalogs):
            lib = "apple-strings"
        elif any(r.endswith(".po") for r in catalogs):
            lib = "gettext"

    footer = sorted(set(component_files(rels, "footer")) | set(footer_markup))
    layout = sorted(r for r in rels if "layout" in tokens(os.path.splitext(r.rsplit("/", 1)[-1])[0])
                    and os.path.splitext(r)[1].lower() in (".tsx", ".jsx", ".js", ".ts", ".vue", ".svelte", ".astro",
                                                           ".dart", ".swift", ".kt", ".html", ".php", ".twig")
                    or r.rsplit("/", 1)[-1] in LAYOUT_NAMES)

    convention = []
    if any(re.search(r"(^|/)app/(.*/)?page\.(tsx|jsx|js|ts)$", r) for r in rels):
        convention.append("next-app-router")
    if "next" in npm and any(re.search(r"(^|/)pages/[^_][^/]*\.(tsx|jsx|js|ts)$", r) for r in rels):
        convention.append("next-pages-router")
    if "expo-router" in npm or any(re.search(r"(^|/)app/_layout\.(tsx|js)$", r) for r in rels) and "expo" in npm:
        convention.append("expo-router")
    if any(n in npm for n in ("react-router-dom", "react-router", "@react-router/dev")):
        convention.append("react-router")
    if "@tanstack/react-router" in npm:
        convention.append("tanstack-router")
    if "@react-navigation/native" in npm:
        convention.append("react-navigation")
    for package in ("go_router", "auto_route", "beamer"):
        if re.search(r"(?m)^\s*%s\s*:" % package, pubspec):
            convention.append("flutter-" + package)
    if any(r.endswith(".controller.ts") for r in rels):
        convention.append("nest-controllers")
    if any(r.endswith("urls.py") for r in rels):
        convention.append("django-urls")
    if any(re.search(r"(^|/)src/routes/.+\+page\.svelte$", r) for r in rels):
        convention.append("sveltekit-routes")
    if any(r.endswith("routes/web.php") for r in rels):
        convention.append("laravel-routes")
    if any(r.endswith((".html", ".htm")) for r in rels) and not convention:
        convention.append("html-files")
    route_files = sorted(r for r in rels if any(p.search(r) for p in ROUTE_FILES))

    return {
        "ui_libs": sorted(set(ui_libs)),
        "tokens": sorted(tokens_found)[:20],
        "i18n": {"lib": lib, "catalogs": catalogs[:50]},
        "footer": footer[:20],
        "checkbox": sorted(component_files(rels, "checkbox"))[:20],
        "layout": layout[:20],
        "routes": {"convention": sorted(set(convention)), "files": route_files[:30]},
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def looks_minified(text):
    return len(text) > 20000 and len(text) > 500 * (text.count("\n") + 1)


def feature_flags(rel, ext, text, manifest):
    """Which pattern families apply to this file (see scan_features)."""
    code, ui = ext in SCAN_EXTS, ext in UI_TEXT_EXTS
    if ext == ".dart":
        ui = "package:flutter/" in text
    elif ext == ".swift":
        ui = bool(re.search(r"^\s*import\s+(?:SwiftUI|UIKit)\b", text, re.M))
    if not manifest and (looks_minified(text) or (
            ext in DOC_EXTS and DOC_DIRS & set(rel.split("/")[:-1]))):
        code = ui = False
    return {"manifest": manifest, "code": code, "ui": ui}


def scan(root, catalog_path, gate=True):
    catalog = _kb.load_catalog(catalog_path)
    warnings = list(catalog.warnings)
    files = walk(root)
    rels = [rel for rel, _, _ in files]

    evidence, forms, legal, footer_markup = {}, [], {}, []
    npm, py_text, pubspec, composer = set(), "", "", ""
    scanned = skipped_large = skipped_binary = 0

    for rel, full, size in files:
        name = rel.rsplit("/", 1)[-1]
        ext = os.path.splitext(name)[1].lower()
        kind = legal_kind_by_path(rel)
        if kind:
            legal[rel] = kind
        manifest = is_manifest(name)
        if name in LOCKFILES or ext in BINARY_EXTS or SKIP_NAME_RE.search(name):
            continue
        if not manifest and ext not in SCAN_EXTS and ext not in UI_TEXT_EXTS and ext not in LEGAL_PAGE_EXTS:
            continue
        if size > MAX_FILE_BYTES:
            skipped_large += 1
            continue
        text = read_text(full)
        if text is None:
            skipped_binary += 1
            continue
        scanned += 1
        index = LineIndex(text)

        scan_features(catalog, rel, text, feature_flags(rel, ext, text, manifest), index, evidence, gate)
        if name == "package.json":
            npm |= npm_dependencies(text)
        elif manifest and name == "pubspec.yaml":
            pubspec += text + "\n"
        elif manifest and name == "composer.json":
            composer += text + "\n"
        elif manifest and name != "Podfile" and not name.startswith("build.gradle") and name != "Package.swift":
            py_text += text.lower() + "\n"
        if rel not in legal:
            heading_kind = legal_kind_by_heading(rel, text)
            if heading_kind:
                legal[rel] = heading_kind
        if ext in MARKUP_EXTS and re.search(r"<footer\b", text, re.I):
            footer_markup.append(rel)
        forms.extend(forms_in(rel, text, index))

    features = []
    for feature_id, items in sorted(evidence.items()):
        if items:
            items.sort(key=lambda e: (e["file"], e["line"], e["match"]))
            features.append({"id": feature_id, "evidence": items})
    forms.sort(key=lambda f: (f["file"], f["line"]))
    stacks, frameworks = detect_stacks(rels, npm, py_text, pubspec, composer)
    return {
        "root": str(root),
        "stacks": stacks,
        "frameworks": frameworks,
        "features": features,
        "legal_pages": [{"file": rel, "kind": kind} for rel, kind in sorted(legal.items())],
        "forms": forms,
        "design": design_inventory(rels, npm, pubspec, footer_markup),
        "stats": {"files_seen": len(files), "files_scanned": scanned, "skipped_large": skipped_large,
                  "skipped_binary": skipped_binary},
        "warnings": sorted(set(warnings)),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="scan_repo.py",
        description="Scan a source tree for features, legal pages, forms and design inventory. Prints JSON.")
    parser.add_argument("root", help="repository root")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG,
                        help="feature catalog JSON (default: references/features/catalog.json)")
    return parser


def main(argv=None):
    args, code = _kb.parse_args(build_parser(), sys.argv[1:] if argv is None else argv)
    if args is None:
        return code
    if not os.path.isdir(args.root):
        return _kb.fail("not a directory: %s" % args.root)
    try:
        result = scan(args.root, args.catalog)
    except _kb.KbError as exc:
        return _kb.fail(str(exc))
    _kb.emit(result)
    return 0


if __name__ == "__main__":
    _kb.setup_stdio()
    sys.exit(main())
