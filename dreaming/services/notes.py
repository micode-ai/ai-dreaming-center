"""Project-aware notes browser: list markdown files in a learning-notes dir."""
from __future__ import annotations
from pathlib import Path
from typing import NamedTuple


class NoteEntry(NamedTuple):
    relative_path: str
    full_path: str
    size: int
    mtime: float


def list_notes(notes_dir: str, max_items: int = 200) -> list[NoteEntry]:
    p = Path(notes_dir)
    if not p.exists() or not p.is_dir():
        return []
    files = sorted(p.rglob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:max_items]
    out: list[NoteEntry] = []
    for f in files:
        try:
            stat = f.stat()
            out.append(NoteEntry(
                relative_path=str(f.relative_to(p)).replace("\\", "/"),
                full_path=str(f),
                size=stat.st_size,
                mtime=stat.st_mtime,
            ))
        except OSError:
            continue
    return out


def read_note(notes_dir: str, relative_path: str) -> str | None:
    """Safe path-traversal-checked read."""
    base = Path(notes_dir).resolve()
    target = (base / relative_path).resolve()
    if not str(target).startswith(str(base)):
        return None
    if not target.exists() or not target.is_file():
        return None
    return target.read_text(encoding="utf-8")
