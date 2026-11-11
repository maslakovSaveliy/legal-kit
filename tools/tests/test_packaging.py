"""Packaging checks: skill frontmatter, plugin manifests, repo layout, privacy.

Self-contained on purpose: the repo root is located from this file, so the test
runs from any working directory. Stdlib only.
"""

import io
import json
import os
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "legal-kit"
SKILL_MD = SKILL_DIR / "SKILL.md"
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = ROOT / ".claude-plugin" / "marketplace.json"

NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
RESERVED_NAME_PREFIXES = ("claude-", "anthropic-")
MAX_DESCRIPTION_LEN = 1024
MAX_SKILL_BODY_LINES = 500

# Substrings that must never appear in the public repo. Extend this tuple when
# a later task discovers another leak pattern.
FORBIDDEN_PATTERNS = (
    "raw/articles",
    "raw/notes",
    "[[",
    "../topics/",
    "/Us" + "ers/",
    "llm" + "-wiki",
    "wiki/concepts",
    "wiki/references",
)

# Directory names skipped at any depth.
EXCLUDED_DIR_NAMES = {".git", ".venv", ".superpowers", ".pytest_cache", "__pycache__"}
# Directories skipped by repo-relative path (posix style). The whole tools/
# tree is out of scope: generator code legitimately knows the private source
# layout, and its tests contain wikilink literals (this file lists the
# forbidden patterns themselves).
EXCLUDED_REL_DIRS = {"tools", "evals/workspace"}
# Files skipped by name at any depth (a `.git` file appears in worktrees and
# submodules, where it is not a directory).
EXCLUDED_FILE_NAMES = {".git"}


def split_frontmatter(text):
    """Return (frontmatter_lines, body_lines) for a document starting with ---."""
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "SKILL.md must start with '---'"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], lines[i + 1:]
    raise AssertionError("SKILL.md frontmatter is not closed with '---'")


def parse_frontmatter(lines):
    """Parse the small YAML subset used by SKILL.md: scalars and one nested map."""
    data = {}
    current_map = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indented = line[0] in " \t"
        key, sep, value = line.strip().partition(":")
        assert sep, f"frontmatter line without ':' -> {line!r}"
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if indented:
            assert current_map is not None, f"indented line without parent -> {line!r}"
            data[current_map][key] = value
        elif value == "":
            current_map = key
            data[key] = {}
        else:
            current_map = None
            data[key] = value
    return data


def load_skill():
    text = SKILL_MD.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    return parse_frontmatter(front), body


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_archive_texts(path, rel):
    """Members of a .tar.gz as ("<rel>!<member>", text): the leak scan reads inside the cards archive."""
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.isfile():
                yield f"{rel}!{member.name}", archive.extractfile(member).read().decode("utf-8", "replace")


def iter_repo_text_files(root=ROOT):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = [
            d
            for d in dirnames
            if d not in EXCLUDED_DIR_NAMES
            and (f"{rel_dir}/{d}" if rel_dir != "." else d) not in EXCLUDED_REL_DIRS
        ]
        for filename in filenames:
            if filename in EXCLUDED_FILE_NAMES:
                continue
            path = Path(dirpath) / filename
            rel = path.relative_to(root).as_posix()
            if filename.endswith(".tar.gz"):
                yield from iter_archive_texts(path, rel)
                continue
            raw = path.read_bytes()
            if b"\x00" in raw:
                continue
            try:
                yield rel, raw.decode("utf-8")
            except UnicodeDecodeError:
                continue


def test_skill_name_is_valid_and_matches_folder():
    front, _ = load_skill()
    name = front.get("name", "")
    assert NAME_RE.match(name), f"invalid skill name: {name!r}"
    assert name == SKILL_DIR.name, "skill name must equal its folder name"


def test_skill_description_limits():
    front, _ = load_skill()
    description = front.get("description", "")
    assert description.strip(), "description is empty"
    assert len(description) <= MAX_DESCRIPTION_LEN, f"description is {len(description)} chars"
    assert "<" not in description and ">" not in description
    assert re.search("[А-Яа-яЁё]", description), "description needs Russian keywords"
    assert re.search("[A-Za-z]{3,}", description), "description needs English words"


def test_skill_body_is_short():
    _, body = load_skill()
    assert len(body) < MAX_SKILL_BODY_LINES


def test_skill_frontmatter_declares_license_and_version():
    front, _ = load_skill()
    assert front.get("license") == "MIT"
    assert front.get("metadata", {}).get("version") == load_json(PLUGIN_JSON)["version"]


def test_no_root_skill_md():
    assert not (ROOT / "SKILL.md").exists(), "SKILL.md must live in skills/legal-kit/, not the repo root"


def test_plugin_manifest_fields():
    plugin = load_json(PLUGIN_JSON)
    assert plugin["name"] == "legal-kit"
    assert re.match(r"^\d+\.\d+\.\d+$", plugin["version"])
    assert plugin["license"] == "MIT"
    assert plugin["author"]["name"] == "maslakovSaveliy"
    assert plugin["repository"] == "https://github.com/maslakovSaveliy/legal-kit"
    assert plugin["description"].strip()


def test_plugin_and_marketplace_names_are_not_reserved():
    names = [load_json(PLUGIN_JSON)["name"]]
    marketplace = load_json(MARKETPLACE_JSON)
    names.append(marketplace["name"])
    names.extend(p["name"] for p in marketplace["plugins"])
    for name in names:
        assert NAME_RE.match(name), f"invalid name: {name!r}"
        assert not name.startswith(RESERVED_NAME_PREFIXES), f"reserved prefix in {name!r}"


def test_marketplace_owner_and_sources():
    marketplace = load_json(MARKETPLACE_JSON)
    assert marketplace["owner"]["name"] == "maslakovSaveliy"
    assert marketplace["description"].strip()
    assert marketplace["plugins"], "marketplace lists no plugins"
    for plugin in marketplace["plugins"]:
        assert plugin["source"].startswith("./"), f"source must start with './': {plugin['source']!r}"
        assert plugin.get("description", "").strip()


def test_no_private_patterns():
    hits = []
    for rel, text in iter_repo_text_files():
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                hits.append(f"{rel}: {pattern!r}")
    assert not hits, "private patterns found:\n" + "\n".join(hits)


def test_no_private_patterns_in_archives(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        data = ("see " + "/Us" + "ers/someone/notes").encode("utf-8")
        info = tarfile.TarInfo("cards/x.md")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    (tmp_path / "cards.tar.gz").write_bytes(buf.getvalue())
    found = dict(iter_repo_text_files(tmp_path))
    assert "/Us" + "ers/" in found["cards.tar.gz!cards/x.md"]


# skills.sh builds a text snapshot of the skill folder and gives up when any of its limits is passed
# (measured 2026-11-04: about 200 files, about 512 KiB per file, 5-6 MB in all; binaries are left out).
# The budget keeps a margin below each limit.
SNAPSHOT_MAX_FILES = 150
SNAPSHOT_MAX_FILE_BYTES = 400_000
SNAPSHOT_MAX_TOTAL_BYTES = 4_000_000
ALLOWED_BINARIES = {"references/jurisdictions/ru/cards.tar.gz"}


def skill_files():
    """(rel, bytes) of the files of the skill folder, as an install copies them."""
    for dirpath, dirnames, filenames in os.walk(SKILL_DIR):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
        for filename in filenames:
            if filename in EXCLUDED_FILE_NAMES or filename == ".DS_Store":
                continue
            path = Path(dirpath) / filename
            yield path.relative_to(SKILL_DIR).as_posix(), path.read_bytes()


def is_binary(rel, raw):
    return rel.endswith(".gz") or b"\x00" in raw


def test_skill_has_no_binaries_but_cards_archive():
    assert {rel for rel, raw in skill_files() if is_binary(rel, raw)} == ALLOWED_BINARIES


def test_skill_fits_skills_sh_snapshot():
    sizes = {rel: len(raw) for rel, raw in skill_files() if not is_binary(rel, raw)}
    big = {rel: size for rel, size in sizes.items() if size > SNAPSHOT_MAX_FILE_BYTES}
    assert len(sizes) <= SNAPSHOT_MAX_FILES, f"{len(sizes)} text files in the skill folder"
    assert not big, f"text files over {SNAPSHOT_MAX_FILE_BYTES} bytes: {big}"
    assert sum(sizes.values()) <= SNAPSHOT_MAX_TOTAL_BYTES, f"{sum(sizes.values())} bytes of text"


def test_readme_counts_match_the_evals():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    evals = len(json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))["evals"])
    queries = json.loads((ROOT / "evals" / "triggers.json").read_text(encoding="utf-8"))
    positive = sum(1 for query in queries if query["should_trigger"])
    assert "%d сценариев" % evals in readme and "%d scenarios" % evals in readme
    assert "%d запросов" % len(queries) in readme and "%d queries" % len(queries) in readme
    assert "%d должны его запускать, %d нет" % (positive, len(queries) - positive) in readme
    assert "%d should trigger it, %d should not" % (positive, len(queries) - positive) in readme
