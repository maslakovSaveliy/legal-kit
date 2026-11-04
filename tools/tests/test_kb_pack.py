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
