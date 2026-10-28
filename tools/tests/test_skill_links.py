"""Link and layout checks for the skill's Markdown: SKILL.md and references/**/*.md.

- SKILL.md body stays under 500 lines.
- Every relative Markdown link resolves to an existing file (anchors are checked for
  SKILL.md and the workflow files).
- Every backticked path starting with `references/` or `scripts/` resolves from the skill
  folder; `<name>`, `*` and `{a,b}` patterns must match at least one file.
- SKILL.md links go straight to files under references/ or scripts/, never to a README.
- Reference files longer than 100 lines open with a table of contents (generated cards
  are exempt).
- The ten workflow files exist and SKILL.md links each of them.

Stdlib only; the repo root is located from this file.
"""

import glob
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "legal-kit"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"
WORKFLOW_DIR = REFERENCES / "workflow"

WORKFLOW_FILES = (
    "intake",
    "recon-repo",
    "recon-prod",
    "recon-stores",
    "applicability",
    "documents",
    "ui-integration",
    "research-rules",
    "safety",
    "report",
    "plan",
)

MAX_SKILL_BODY_LINES = 500
TOC_MIN_LINES = 100
TOC_MARKER_RE = re.compile(r"^(?:#{1,6}\s+)?(?:contents|table of contents|оглавление|содержание)\b", re.I)
# Generated requirement cards are read one at a time and carry no TOC by design of the
# knowledge generator; their links are still checked.
TOC_EXCLUDED_DIRS = ("cards",)

LINK_RE = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)\)")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
ANCHOR_RE = re.compile(r"\]\(#([^)\s]+)\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
CHECKED_PREFIXES = ("references/", "scripts/")


# ---------------------------------------------------------------- helpers


def rel(path):
    return path.relative_to(ROOT).as_posix()


def markdown_files():
    return [SKILL_MD, *sorted(REFERENCES.rglob("*.md"))]


def own_files():
    """Files whose in-page anchors are checked too."""
    return [SKILL_MD, *(WORKFLOW_DIR / f"{name}.md" for name in WORKFLOW_FILES)]


def body_lines(text):
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[i + 1:]
    return lines


def unfenced(text):
    """Text with fenced code blocks blanked out (line numbers kept)."""
    out, fenced = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else line)
    return "\n".join(out)


def headings(text):
    found = []
    for line in unfenced(text).splitlines():
        match = HEADING_RE.match(line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def github_anchor(title):
    """GitHub-style heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    plain = re.sub(r"`([^`]*)`", r"\1", title)
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", plain)
    kept = [ch for ch in plain.lower()
            if ch.isalnum() or ch in "-_ " or unicodedata.category(ch).startswith("M")]
    return "".join(kept).replace(" ", "-")


def heading_anchors(text):
    anchors, seen = set(), {}
    for _, title in headings(text):
        base = github_anchor(title)
        count = seen.get(base, 0)
        anchors.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return anchors


def relative_links(path):
    """(target path or '', anchor or '') for every relative link outside code fences."""
    links = []
    for target in LINK_RE.findall(unfenced(path.read_text(encoding="utf-8"))):
        if SCHEME_RE.match(target) or "{{" in target or "}}" in target:
            continue
        file_part, _, anchor = target.partition("#")
        links.append((file_part, anchor))
    return links


def expand_braces(pattern):
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    head, tail = pattern[:match.start()], pattern[match.end():]
    out = []
    for option in match.group(1).split(","):
        out.extend(expand_braces(head + option + tail))
    return out


def backticked_paths(path):
    """First token of every backticked span that starts with references/ or scripts/."""
    found = []
    for span in BACKTICK_RE.findall(path.read_text(encoding="utf-8")):
        token = span.strip().split()[0] if span.strip() else ""
        token = token.rstrip(".,;:)")
        if token.startswith(CHECKED_PREFIXES):
            found.append(token)
    return found


def path_exists_from_skill(token):
    """True when every brace alternative matches at least one existing path."""
    for alternative in expand_braces(token):
        if any(ch in alternative for ch in "<*?["):
            pattern = re.sub(r"<[^<>]*>", "*", alternative)
            if not glob.glob(str(SKILL_DIR / pattern)):
                return False
        elif not (SKILL_DIR / alternative).exists():
            return False
    return True


def toc_paths():
    """Reference files (SKILL.md is the entry point and is read whole, so it has no TOC)."""
    paths = []
    for path in sorted(REFERENCES.rglob("*.md")):
        if not any(part in TOC_EXCLUDED_DIRS for part in path.relative_to(REFERENCES).parts):
            paths.append(path)
    return paths


# ---------------------------------------------------------------- tests


def test_skill_md_body_is_under_limit():
    lines = body_lines(SKILL_MD.read_text(encoding="utf-8"))
    assert len(lines) < MAX_SKILL_BODY_LINES, f"SKILL.md body has {len(lines)} lines"


@pytest.mark.parametrize("name", WORKFLOW_FILES)
def test_workflow_file_exists(name):
    assert (WORKFLOW_DIR / f"{name}.md").is_file(), f"missing references/workflow/{name}.md"


@pytest.mark.parametrize("path", markdown_files(), ids=rel)
def test_relative_links_resolve(path):
    broken = []
    for file_part, _ in relative_links(path):
        if file_part and not (path.parent / file_part).exists():
            broken.append(file_part)
    assert not broken, f"{rel(path)}: links to missing files: {sorted(set(broken))}"


@pytest.mark.parametrize("path", own_files(), ids=rel)
def test_link_anchors_resolve(path):
    if not path.is_file():
        pytest.fail(f"{rel(path)} does not exist")
    broken = []
    for file_part, anchor in relative_links(path):
        if not anchor:
            continue
        target = (path.parent / file_part) if file_part else path
        if target.suffix != ".md" or not target.is_file():
            continue
        if anchor not in heading_anchors(target.read_text(encoding="utf-8")):
            broken.append(f"{file_part}#{anchor}")
    assert not broken, f"{rel(path)}: anchors without a heading: {broken}"


@pytest.mark.parametrize("path", markdown_files(), ids=rel)
def test_backticked_skill_paths_exist(path):
    missing = sorted({token for token in backticked_paths(path) if not path_exists_from_skill(token)})
    assert not missing, f"{rel(path)}: backticked paths that do not exist under skills/legal-kit/: {missing}"


def test_skill_md_links_go_directly_to_reference_or_script_files():
    problems = []
    for file_part, _ in relative_links(SKILL_MD):
        if not file_part:
            continue
        target = (SKILL_MD.parent / file_part).resolve()
        try:
            inside = target.relative_to(SKILL_DIR.resolve()).as_posix()
        except ValueError:
            problems.append(f"{file_part}: outside the skill folder")
            continue
        if not inside.startswith(CHECKED_PREFIXES):
            problems.append(f"{file_part}: not under references/ or scripts/")
        elif not target.is_file():
            problems.append(f"{file_part}: not a file")
        elif target.name.lower() == "readme.md":
            problems.append(f"{file_part}: links an index README instead of the file itself")
    assert not problems, "SKILL.md links:\n" + "\n".join(problems)


def test_skill_md_links_every_workflow_file():
    linked = {(SKILL_MD.parent / f).resolve() for f, _ in relative_links(SKILL_MD) if f}
    missing = [n for n in WORKFLOW_FILES if (WORKFLOW_DIR / f"{n}.md").resolve() not in linked]
    assert not missing, f"SKILL.md does not link workflow files: {missing}"


@pytest.mark.parametrize("path", toc_paths(), ids=rel)
def test_long_files_start_with_toc(path):
    text = path.read_text(encoding="utf-8")
    lines = body_lines(text)
    if len(lines) <= TOC_MIN_LINES:
        return
    # The top of the file: everything before the first level-2 heading that is not the TOC itself.
    top = []
    for line in unfenced("\n".join(lines)).splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 2 and not TOC_MARKER_RE.match(match.group(2)):
            break
        top.append(line)
    assert any(TOC_MARKER_RE.match(line.strip()) for line in top), (
        f"{rel(path)} has {len(lines)} lines but no table of contents before its first section"
    )
    anchors = ANCHOR_RE.findall("\n".join(top))
    assert len(anchors) >= 2, f"{rel(path)}: table of contents has fewer than two links"
    known = heading_anchors(text)
    broken = [a for a in anchors if a not in known]
    assert not broken, f"{rel(path)}: table of contents links without a heading: {broken}"
