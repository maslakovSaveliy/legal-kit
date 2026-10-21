#!/usr/bin/env python3
"""Build the sanitized knowledge pack of a jurisdiction from the requirement cards of a knowledge base.

    build_knowledge.py --wiki <topic> --build-refs <build_refs.py> --out skills/legal-kit/references/jurisdictions/ru [--check]

--build-refs is the table module of the source base (its directory map DIRS and its short triggers TRIGGER);
it is read, never copied, and is required together with --wiki.

Without --check the pack is written into --out. With --check it is built into a temporary
directory and compared with --out; any difference gives exit code 1. Exit code 2 means the
input could not be read or is inconsistent. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb import GENERATOR_VERSION  # noqa: E402
from kb.emit_cards import (  # noqa: E402
    brief, dir_letter, is_generated_card, load_templates, write_base, write_card, write_requirements,
)
from kb.legacy import load_build_refs  # noqa: E402
from kb.links import LinkCtx, raw_url_map  # noqa: E402
from kb.parse import header_bytes, load_card  # noqa: E402
from kb.templates import TemplateError, build_templates, generated_paths as template_paths  # noqa: E402

GENERATED_FILES = ("requirements.jsonl", "BASE.md")
TABLE_NAME = "build_refs.py"
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class BuildError(Exception):
    """The knowledge base is missing something the generator needs."""


def source_digest(topic: Path, build_refs: Path) -> str:
    """SHA-256 over the source files the build reads, independent of git and of file times.

    The digest covers, in sorted order of their posix paths relative to the topic, every card and
    every template in full, the frontmatter of every raw file (the only part read for the link
    map) and, as ``build_refs.py``, the table module with the directory map and the triggers.
    """
    files = {}
    for path in (topic / "wiki" / "concepts").glob("*.md"):
        if path.name != "_index.md":
            files[path] = path.read_bytes()
    for path in (topic / "wiki" / "references").glob("shablon-*.md"):
        files[path] = path.read_bytes()
    for path in (topic / "raw").rglob("*.md"):
        if path.name != "_index.md":
            files[path] = header_bytes(path)
    named = {path.relative_to(topic).as_posix(): data for path, data in files.items()}
    if Path(build_refs).is_file():
        named[TABLE_NAME] = Path(build_refs).read_bytes()
    digest = hashlib.sha256()
    for name, data in sorted(named.items()):
        digest.update(name.encode("utf-8") + b"\0" + data + b"\0")
    return digest.hexdigest()


def load_cards(topic: Path) -> list:
    folder = topic / "wiki" / "concepts"
    if not folder.is_dir():
        raise BuildError(f"no cards folder: {folder}")
    cards = [load_card(path) for path in sorted(folder.glob("*.md")) if path.name != "_index.md"]
    if not cards:
        raise BuildError(f"no cards in {folder}")
    return cards


def build_pack(topic, out, build_refs) -> dict:
    """Write requirements.jsonl, cards/*.md and BASE.md into ``out`` and return the build facts."""
    topic, out = Path(topic), Path(out)
    cards = load_cards(topic)
    try:
        refs = load_build_refs(build_refs)
        letters = dir_letter(refs.DIRS)
    except (FileNotFoundError, AttributeError, ValueError) as error:
        raise BuildError(str(error)) from error

    slugs = {card.slug for card in cards}
    problems = [f"card without directory: {s}" for s in sorted(slugs - set(letters))]
    problems += [f"directory lists missing card: {s}" for s in sorted(set(letters) - slugs)]
    problems += [f"card without trigger: {s}" for s in sorted(slugs - set(refs.TRIGGER))]
    if problems:
        raise BuildError("; ".join(problems))

    templates_by_card, template_dates = load_templates(topic)
    unknown = sorted(set(templates_by_card) - slugs)
    if unknown:
        raise BuildError(f"templates list unknown cards: {', '.join(unknown)}")

    ctx = LinkCtx(
        card_slugs=slugs,
        template_slugs=set(template_dates),
        raw_urls=raw_url_map(topic),
        card_href=lambda slug: f"{slug}.md",
        template_href=lambda slug: f"../templates/{slug}/text.md",
    )

    dates = [d for card in cards for d in (card.fm.get("checked", ""), card.fm.get("updated", "")) if DATE.fullmatch(d)]
    dates += [d for d in template_dates.values() if DATE.fullmatch(d)]
    if not dates:
        raise BuildError("no dates found in cards and templates")

    records = [
        brief(card, refs.TRIGGER[card.slug], letters[card.slug], templates_by_card, ctx) for card in cards
    ]
    write_requirements(records, out)
    cards_dir = out / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    for stale in cards_dir.glob("*.md"):
        if stale.stem not in slugs and is_generated_card(stale):
            stale.unlink()
    for card in cards:
        write_card(card, ctx, out)
    try:  # templates/, elements.json, placeholders.json, forbidden-clauses.json (kb/templates.py)
        build_templates(topic, out, ctx)
    except TemplateError as error:
        raise BuildError(str(error)) from error

    meta = {
        "base_date": max(dates),
        "source_sha256": source_digest(topic, build_refs),
        "requirements": len(records),
        "cards": len(cards),
        "templates": len(template_dates),
        "generator_version": GENERATOR_VERSION,
    }
    write_base(meta, out)
    return meta


def _generated_paths(root: Path) -> set:
    paths = {name for name in GENERATED_FILES if (root / name).is_file()}
    if (root / "cards").is_dir():
        paths |= {f"cards/{p.name}" for p in (root / "cards").glob("*.md") if is_generated_card(p)}
    return paths | template_paths(root)


def check_pack(topic, out, build_refs) -> list:
    """Build into a temporary directory and list how ``out`` differs; an empty list means it is current."""
    out = Path(out)
    with tempfile.TemporaryDirectory() as tmp:
        fresh_root = Path(tmp) / "ru"
        build_pack(topic, fresh_root, build_refs)
        fresh, existing = _generated_paths(fresh_root), _generated_paths(out)
        differences = []
        for rel in sorted(fresh | existing):
            if rel not in existing:
                differences.append(f"missing: {rel}")
            elif rel not in fresh:
                differences.append(f"unexpected: {rel}")
            elif (fresh_root / rel).read_bytes() != (out / rel).read_bytes():
                differences.append(f"differs: {rel}")
        return differences


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the knowledge pack from requirement cards.")
    parser.add_argument("--wiki", required=True, help="topic root of the knowledge base")
    parser.add_argument("--build-refs", help="path to the source base's build_refs.py (directory map DIRS and "
                                             "short triggers TRIGGER); required together with --wiki")
    parser.add_argument("--out", required=True, help="pack directory, e.g. skills/legal-kit/references/jurisdictions/ru")
    parser.add_argument("--check", action="store_true", help="compare a fresh build with --out; exit 1 on differences")
    args = parser.parse_args(argv)
    topic = Path(args.wiki)
    if not topic.is_dir():
        print(f"error: not a directory: {topic}", file=sys.stderr)
        return 2
    if not args.build_refs:
        print("error: --build-refs is required together with --wiki: pass the path to the source base's "
              "build_refs.py, the module with the directory map (DIRS) and the short triggers (TRIGGER)",
              file=sys.stderr)
        return 2
    try:
        if args.check:
            differences = check_pack(topic, args.out, args.build_refs)
            for line in differences:
                print(line)
            if differences:
                print(f"pack is out of date: {len(differences)} difference(s)", file=sys.stderr)
                return 1
            print("pack is current")
            return 0
        meta = build_pack(topic, args.out, args.build_refs)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"built {meta['requirements']} requirements, {meta['cards']} cards into {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
