"""Tests for the knowledge pack layout: requirement shards, the cards archive and scripts/kb.py."""

import gzip
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

# Preload before the scripts directory joins sys.path: select.py there must not
# shadow the stdlib module of the same name.
import select  # noqa: F401
import selectors  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "legal-kit" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import _kb  # noqa: E402


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def make_archive(path, members, symlinks=()):
    """A cards.tar.gz with the given {name: text} members (and symlink members by name)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, text in members.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name in symlinks:
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(buf.getvalue()))
    return path


CARD_A = "---\nid: ru:a\n---\n\n# Карточка A\n\n## Что проверить\n\nСогласие на обработку.\n\n## Источники\n\nСм. [b](b.md).\n"
CARD_B = "---\nid: ru:b\n---\n\n# Карточка B\n\nТекст про оферту.\n"


# ---------------------------------------------------------------- requirement shards

def test_requirements_shards_read_sorted_by_id(tmp_path):
    write_jsonl(tmp_path / "requirements" / "A.jsonl", [{"id": "ru:b", "dir": "A"}])
    write_jsonl(tmp_path / "requirements" / "B.jsonl", [{"id": "ru:a", "dir": "B"}])
    assert list(_kb.load_requirements(tmp_path)) == ["ru:a", "ru:b"]


def test_requirements_shards_win_over_legacy_file(tmp_path):
    write_jsonl(tmp_path / "requirements" / "A.jsonl", [{"id": "ru:new"}])
    write_jsonl(tmp_path / "requirements.jsonl", [{"id": "ru:old"}])
    assert list(_kb.load_requirements(tmp_path)) == ["ru:new"]


def test_requirements_legacy_single_file_still_read(tmp_path):
    write_jsonl(tmp_path / "requirements.jsonl", [{"id": "ru:z"}, {"id": "ru:y"}])
    assert sorted(_kb.load_requirements(tmp_path)) == ["ru:y", "ru:z"]


def test_requirements_duplicate_id_across_shards_fails(tmp_path):
    write_jsonl(tmp_path / "requirements" / "A.jsonl", [{"id": "ru:a"}])
    write_jsonl(tmp_path / "requirements" / "B.jsonl", [{"id": "ru:a"}])
    with pytest.raises(_kb.KbError) as error:
        _kb.load_requirements(tmp_path)
    assert "A.jsonl" in str(error.value) and "B.jsonl" in str(error.value)


def test_requirements_bad_line_names_shard(tmp_path):
    shard = tmp_path / "requirements" / "C.jsonl"
    shard.parent.mkdir(parents=True)
    shard.write_text('{"id": "ru:a"}\nnot json\n', encoding="utf-8")
    with pytest.raises(_kb.KbError, match=r"C\.jsonl line 2"):
        _kb.load_requirements(tmp_path)


# ---------------------------------------------------------------- cards archive

def test_load_cards_reads_archive(tmp_path):
    make_archive(tmp_path / "cards.tar.gz", {"cards/b.md": CARD_B, "cards/a.md": CARD_A})
    cards = _kb.load_cards(tmp_path)
    assert list(cards) == ["ru:a", "ru:b"]
    assert cards["ru:a"] == CARD_A and cards["ru:b"] == CARD_B


def test_load_cards_missing_archive_fails(tmp_path):
    with pytest.raises(_kb.KbError, match="cards.tar.gz"):
        _kb.load_cards(tmp_path)


def test_load_cards_corrupt_archive_fails(tmp_path):
    (tmp_path / "cards.tar.gz").write_bytes(b"not an archive")
    with pytest.raises(_kb.KbError):
        _kb.load_cards(tmp_path)


@pytest.mark.parametrize("name", ["../x.md", "/abs.md", "cards/A.md", "cards/sub/x.md", "notes.md"])
def test_load_cards_rejects_bad_member(tmp_path, name):
    make_archive(tmp_path / "cards.tar.gz", {"cards/a.md": CARD_A, name: "x"})
    with pytest.raises(_kb.KbError):
        _kb.load_cards(tmp_path)


def test_load_cards_rejects_symlink_member(tmp_path):
    make_archive(tmp_path / "cards.tar.gz", {"cards/a.md": CARD_A}, symlinks=["cards/b.md"])
    with pytest.raises(_kb.KbError):
        _kb.load_cards(tmp_path)


@pytest.mark.parametrize("ref", ["ru:soglasie-pdn", "soglasie-pdn", "soglasie-pdn.md", "cards/soglasie-pdn.md"])
def test_card_ref_forms(ref):
    assert _kb.card_ref(ref) == "ru:soglasie-pdn"


@pytest.mark.parametrize("ref", ["", "ru:", "../etc/passwd", "ru:Big", "cards/a/b.md", "a b"])
def test_card_ref_rejects_garbage(ref):
    with pytest.raises(_kb.KbError):
        _kb.card_ref(ref)


# ---------------------------------------------------------------- scripts/kb.py

KB_PY = SCRIPTS / "kb.py"


def run_kb(*args, cwd=None):
    import subprocess
    return subprocess.run([sys.executable, str(KB_PY), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=cwd)


@pytest.fixture
def pack(tmp_path):
    kb = tmp_path / "kb"
    make_archive(kb / "cards.tar.gz", {"cards/a.md": CARD_A, "cards/b.md": CARD_B})
    return kb


def test_kb_card_prints_text(pack):
    for ref in ("ru:a", "a", "cards/a.md"):
        result = run_kb("card", ref, "--kb", pack)
        assert result.returncode == 0, result.stderr
        assert result.stdout == CARD_A


def test_kb_card_section(pack):
    result = run_kb("card", "ru:a", "--section", "Что проверить", "--kb", pack)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "## Что проверить\n\nСогласие на обработку.\n\n"


def test_kb_card_unknown_section_lists_sections(pack):
    result = run_kb("card", "ru:a", "--section", "Нет такой", "--kb", pack)
    assert result.returncode == 2
    error = json.loads(result.stdout)["error"]
    assert "Что проверить" in error and "Источники" in error


def test_kb_card_unknown_id_exit_2(pack):
    result = run_kb("card", "ru:nope", "--kb", pack)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "no card ru:nope; try: kb.py search <words>"}
    assert "Traceback" not in result.stderr


def test_kb_search_case_insensitive_and_max(pack):
    result = run_kb("search", "ОФЕРТ", "--kb", pack)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [{"id": "ru:b", "line": 7, "text": "Текст про оферту."}]
    limited = json.loads(run_kb("search", "карточка", "--max", "1", "--kb", pack).stdout)
    assert [hit["id"] for hit in limited] == ["ru:a"]


def test_kb_list(pack):
    result = run_kb("list", "--kb", pack)
    assert json.loads(result.stdout) == [{"id": "ru:a", "card": "cards/a.md"}, {"id": "ru:b", "card": "cards/b.md"}]


def test_kb_extract_writes_card_files(pack, tmp_path):
    out = tmp_path / "out"
    result = run_kb("extract", "--to", out, "--kb", pack)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"extracted": 2, "dir": str(out)}
    assert (out / "cards" / "a.md").read_text(encoding="utf-8") == CARD_A
    assert sorted(p.name for p in (out / "cards").iterdir()) == ["a.md", "b.md"]


def test_kb_extract_writes_only_card_files(tmp_path):
    kb = tmp_path / "kb"
    make_archive(kb / "cards.tar.gz", {"cards/a.md": CARD_A, "../evil.md": "x"})
    out = tmp_path / "out"
    result = run_kb("extract", "--to", out, "--kb", kb)
    assert result.returncode == 2
    assert not (tmp_path / "evil.md").exists() and not out.exists()


def test_kb_missing_archive_exit_2(tmp_path):
    result = run_kb("list", "--kb", tmp_path)
    assert result.returncode == 2 and "cards.tar.gz" in json.loads(result.stdout)["error"]


def test_kb_help():
    result = run_kb("--help")
    assert result.returncode == 0 and "card" in result.stdout and "extract" in result.stdout


# ---------------------------------------------------------------- the bundled pack

REAL_KB = ROOT / "skills" / "legal-kit" / "references" / "jurisdictions" / "ru"


def test_tar_fallback_matches_kb_card():
    import shutil
    import subprocess
    if not shutil.which("tar"):
        pytest.skip("no tar on PATH")
    cards = _kb.load_cards(REAL_KB)
    first = next(iter(cards))
    member = "cards/%s.md" % first[3:]
    result = subprocess.run(["tar", "-xzOf", str(REAL_KB / "cards.tar.gz"), member], capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode("utf-8") == cards[first]


def test_every_requirement_has_its_card_in_the_archive():
    requirements, cards = _kb.load_requirements(REAL_KB), _kb.load_cards(REAL_KB)
    assert sorted(requirements) == sorted(cards)
    assert all(record["card"] == "cards/%s.md" % key[3:] for key, record in requirements.items())


def test_card_links_resolve_inside_archive():
    import re
    cards = _kb.load_cards(REAL_KB)
    names = {key[3:] + ".md" for key in cards}
    templates = {p.name for p in (REAL_KB / "templates").iterdir() if p.is_dir()}
    broken = []
    for key, text in cards.items():
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            target = target.split("#", 1)[0]
            if target.startswith(("http://", "https://")) or not target:
                continue
            template = re.fullmatch(r"\.\./templates/([a-z0-9-]+)/text\.md", target)
            if not (target in names or (template and template.group(1) in templates)):
                broken.append("%s: %s" % (key, target))
    assert not broken, "\n".join(broken[:20])


def test_requirements_empty_shard_dir_falls_back_to_legacy_file(tmp_path):
    (tmp_path / "requirements").mkdir()
    write_jsonl(tmp_path / "requirements.jsonl", [{"id": "ru:old"}])
    assert list(_kb.load_requirements(tmp_path)) == ["ru:old"]


def test_requirements_empty_shard_dir_without_legacy_fails(tmp_path):
    (tmp_path / "requirements").mkdir()
    with pytest.raises(_kb.KbError, match="requirements"):
        _kb.load_requirements(tmp_path)


def test_docs_tar_fallback_runs_from_the_pack_folder():
    """GNU tar of Git for Windows reads `C:/…/cards.tar.gz` as host:path; the docs name the archive relatively."""
    import re
    skill = ROOT / "skills" / "legal-kit"
    docs = [skill / "SKILL.md", *sorted((skill / "references" / "workflow").glob("*.md"))]
    commands = [(p.name, m) for p in docs for m in re.findall(r"`[^`]*tar -xzOf[^`]*`", p.read_text(encoding="utf-8"))]
    assert commands
    bad = [(name, cmd) for name, cmd in commands if "cd <skill>/references/jurisdictions/ru" not in cmd
           or "tar -xzOf cards.tar.gz cards/" not in cmd]
    assert not bad, bad


def test_skill_md_explains_template_links_inside_cards():
    text = (ROOT / "skills" / "legal-kit" / "SKILL.md").read_text(encoding="utf-8")
    assert "`../templates/<t>/text.md`" in text and "references/jurisdictions/ru/templates/<t>/text.md" in text
