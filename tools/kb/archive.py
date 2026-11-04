"""The deterministic cards archive of the pack (cards.tar.gz).

The bytes depend only on the member names and contents: USTAR entries in name order with zero
times, owners and fixed modes, gzip without a timestamp. A rebuild whose members did not change
keeps the existing file, so a different zlib on another machine does not rewrite it.
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path


def pack(files: dict) -> bytes:
    """``{member: bytes}`` -> gzip-compressed tar bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(files):
            data = files[name]
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return gzip.compress(buf.getvalue(), compresslevel=9, mtime=0)


def members(path) -> dict:
    """``{member: bytes}`` of the regular files of an archive, in name order."""
    found = {}
    with tarfile.open(path, "r:gz") as tar:
        for info in tar.getmembers():
            if info.isfile():
                found[info.name] = tar.extractfile(info).read()
    return {name: found[name] for name in sorted(found)}


def write_if_changed(path, files: dict) -> bool:
    """Write the archive of ``files`` unless ``path`` already holds exactly these members."""
    path = Path(path)
    if path.is_file():
        try:
            if members(path) == {name: files[name] for name in sorted(files)}:
                return False
        except (OSError, EOFError, tarfile.TarError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack(files))
    return True
