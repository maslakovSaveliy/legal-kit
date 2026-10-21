#!/usr/bin/env python3
"""Check the output of one eval run with the skill's own scripts.

A run directory is the project the skill worked on. It must contain
`.legal/report.json`; documents the skill drafted live in `.legal/drafts/`.

The check runs two scripts from the skill:

* `report.py verify .legal/report.json --kb <ru dir> [--sources S] [--answers .legal/answers.json] [--today D]`
  (`--answers` is passed when the file exists: a sector requirement then needs a sector the owner confirmed)
* `check_docs.py <drafts> --public <file> [--public <file> ...] --answers .legal/answers.json`

Drafts are the files in `.legal/drafts/` (plus `--drafts` globs). Public files
are the project files the run changed outside `.legal/` (the paths in
`.legal/state.json` and, when the run directory is the top of its own git
repository, the files changed since its baseline commit) and the paste-ready
artifacts in `.legal/paste/`. check_docs.py decides which issues block: a
placeholder blocks only in a public file (a requisite the owner withheld in
`owner.withheld` does not), a `risk` clause never does.

Exit codes: 0 both checks pass, 1 a check found violations, 2 the check could
not run or a script misbehaved (scripts or inputs missing, exit code above 1,
unreadable output, timeout).

Stdlib only.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCRIPTS = ROOT / "skills" / "legal-kit" / "scripts"
DEFAULT_KB = ROOT / "skills" / "legal-kit" / "references" / "jurisdictions" / "ru"
DRAFT_SUFFIXES = (".md", ".txt", ".html")
DEFAULT_TIMEOUT = 120
MAX_PUBLIC_BYTES = 2 * 1024 * 1024

EXIT_PASS, EXIT_FAIL, EXIT_ERROR = 0, 1, 2


class ScriptError(Exception):
    """A skill script could not be run or did not behave as its contract says."""


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run_dir", type=Path, help="project directory the skill worked on")
    parser.add_argument("--scripts-dir", type=Path, default=DEFAULT_SCRIPTS,
                        help="directory with report.py and check_docs.py")
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB,
                        help="jurisdiction pack passed to report.py verify")
    parser.add_argument("--today", help="YYYY-MM-DD passed to report.py verify")
    parser.add_argument("--drafts", action="append", default=[], metavar="GLOB",
                        help="extra draft files, glob relative to run_dir (repeatable)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="seconds one script may run (default %(default)s)")
    args = parser.parse_args(argv)
    # The scripts run with cwd=run_dir, so every path handed to them must be absolute.
    args.run_dir = args.run_dir.resolve()
    args.scripts_dir = args.scripts_dir.resolve()
    args.kb = args.kb.resolve()
    return args


def run_script(script, script_args, args):
    try:
        return subprocess.run(
            [sys.executable, str(script), *map(str, script_args)],
            cwd=str(args.run_dir), capture_output=True, text=True, timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        raise ScriptError(f"{script.name} did not finish in {args.timeout:g} seconds")


def tail(text, limit=1500):
    text = text.strip()
    return text if len(text) <= limit else "...\n" + text[-limit:]


def find_drafts(run_dir, extra_globs):
    drafts = set()
    drafts_dir = run_dir / ".legal" / "drafts"
    if drafts_dir.is_dir():
        drafts.update(p for p in drafts_dir.rglob("*") if p.is_file() and p.suffix in DRAFT_SUFFIXES)
    for pattern in extra_globs:
        drafts.update(p for p in run_dir.glob(pattern) if p.is_file())
    return sorted(drafts)


def is_text_file(path):
    try:
        if not path.is_file() or path.stat().st_size > MAX_PUBLIC_BYTES:
            return False
        with path.open("rb") as handle:
            return b"\0" not in handle.read(8192)
    except OSError:
        return False


def inside(run_dir, relative):
    """The file `relative` names inside run_dir, or None for an absolute path or one that leaves run_dir."""
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
        return None
    path = (run_dir / relative).resolve()
    try:
        path.relative_to(run_dir)
    except ValueError:
        return None
    return path


def managed_paths(run_dir):
    """Paths recorded in .legal/state.json (managed[].path); an unreadable file gives none."""
    try:
        state = json.loads((run_dir / ".legal" / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    managed = state.get("managed") if isinstance(state, dict) else None
    return [entry.get("path") for entry in managed or [] if isinstance(entry, dict)]


def git_changed_paths(run_dir):
    """Files changed or added since the last commit, when run_dir is the top of its own git repository."""
    def git(*command):
        return subprocess.run(["git", "-C", str(run_dir), *command], capture_output=True, text=True, timeout=60)

    try:
        top = git("rev-parse", "--show-toplevel")
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != run_dir:
            return []
        status = git("status", "--porcelain", "--untracked-files=all", "-z")
    except (OSError, subprocess.TimeoutExpired):
        return []
    if status.returncode != 0:
        return []
    paths, entries = [], iter(status.stdout.split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            next(entries, None)  # -z lists the source of a rename or copy as the next entry
        if "D" not in code:
            paths.append(path)
    return paths


def find_public(run_dir):
    """Public files: changed project files outside .legal/ and the paste artifacts in .legal/paste/."""
    legal, paste = run_dir / ".legal", run_dir / ".legal" / "paste"
    public = set()
    for relative in managed_paths(run_dir) + git_changed_paths(run_dir):
        path = inside(run_dir, relative)
        if path is None or path == legal or legal in path.parents:
            continue
        public.add(path)
    if paste.is_dir():
        public.update(path for path in (p.resolve() for p in paste.rglob("*")) if run_dir in path.parents)
    return sorted(p for p in public if is_text_file(p))


def issues_from(stdout):
    """Return the issue list of a check_docs answer, or None when it is not `{"issues": [...]}`."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
        return None
    return data["issues"]


def check_verify(args, report, sources, answers):
    cmd = ["verify", report, "--kb", args.kb]
    if sources.is_file():
        cmd += ["--sources", sources]
    if answers.is_file():
        cmd += ["--answers", answers]
    if args.today:
        cmd += ["--today", args.today]
    result = run_script(args.scripts_dir / "report.py", cmd, args)
    print(f"report.py verify: exit {result.returncode}")
    if result.returncode > 1:
        print(tail(result.stdout + "\n" + result.stderr), file=sys.stderr)
        raise ScriptError(f"report.py verify exited {result.returncode}; its contract is 0 or 1")
    if result.returncode == 1:
        print(tail(result.stdout + "\n" + result.stderr))
    return result.returncode == 0


def check_docs(args, answers, drafts, public):
    if not drafts and not public:
        print("check_docs.py: skipped, no drafts in .legal/drafts/ and no changed public files")
        return True
    cmd = [*drafts]
    for path in public:  # check_docs.py takes one file per --public
        cmd += ["--public", path]
    result = run_script(args.scripts_dir / "check_docs.py", [*cmd, "--answers", answers], args)
    issues = issues_from(result.stdout)
    if result.returncode > 1:
        print(tail(result.stdout + "\n" + result.stderr), file=sys.stderr)
        raise ScriptError(f"check_docs.py exited {result.returncode}; its contract is 0 or 1")
    if issues is None:
        print(tail(result.stdout + "\n" + result.stderr), file=sys.stderr)
        raise ScriptError("check_docs.py printed no JSON object with an `issues` list")
    # An issue without the flag counts as blocking.
    blocking = [i for i in issues if not (isinstance(i, dict) and i.get("blocking") is False)]
    print(f"check_docs.py: {len(drafts)} drafts, {len(public)} public files, {len(issues)} issues, "
          f"{len(blocking)} blocking, exit {result.returncode}")
    for issue in blocking:
        print(f"  {issue}")
    if result.returncode == 1 and not blocking:
        print("  check_docs.py exited 1 without listing an issue that blocks")
        return False
    return not blocking


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    scripts = args.scripts_dir

    missing = [name for name in ("report.py", "check_docs.py") if not (scripts / name).is_file()]
    if missing:
        print(f"check_run: cannot run, missing in {scripts}: {', '.join(missing)}. "
              "The skill scripts are not written yet.", file=sys.stderr)
        return EXIT_ERROR

    legal = args.run_dir / ".legal"
    report = legal / "report.json"
    if not report.is_file():
        print(f"check_run: no report at {report}", file=sys.stderr)
        return EXIT_ERROR

    drafts = find_drafts(args.run_dir, args.drafts)
    draft_set = set(drafts)
    public = [p for p in find_public(args.run_dir) if p not in draft_set]
    answers = legal / "answers.json"
    if (drafts or public) and not answers.is_file():
        print(f"check_run: documents found but no answers file at {answers}", file=sys.stderr)
        return EXIT_ERROR

    try:
        verify_ok = check_verify(args, report, legal / "sources.json", answers)
        docs_ok = check_docs(args, answers, drafts, public)
    except ScriptError as err:
        print(f"check_run: ERROR, {err}", file=sys.stderr)
        return EXIT_ERROR
    if verify_ok and docs_ok:
        print("check_run: PASS")
        return EXIT_PASS
    print("check_run: FAIL")
    return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
