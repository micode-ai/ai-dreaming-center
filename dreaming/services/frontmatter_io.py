"""Tiny utilities for read-modify-write of YAML frontmatter on a Markdown file.

Used by the inline status-change / GitHub-link persistence on Findings and
Ideas pages — keeps the rewrite logic in one place instead of inlining a
regex.subn in every endpoint.
"""
from __future__ import annotations
import re
from pathlib import Path


_FIELD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _field_pattern(key: str) -> re.Pattern[str]:
    pat = _FIELD_RE_CACHE.get(key)
    if pat is None:
        pat = re.compile(rf"(?m)^{re.escape(key)}\s*:\s*.*$")
        _FIELD_RE_CACHE[key] = pat
    return pat


def set_frontmatter_field(path: Path, key: str, value: str) -> bool:
    """Set (or insert) `key: value` in the YAML frontmatter of `path`.

    - If the field already exists, replaces the entire line.
    - If the file has a frontmatter block but no such key, inserts the
      line just before the closing `---`.
    - If the file has no frontmatter at all, prepends one with this key.

    Returns True on success.
    """
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new_line = f"{key}: {value}"
    pat = _field_pattern(key)
    new_text, n = pat.subn(new_line, text, count=1)
    if n == 0:
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end > 0:
                new_text = text[:end] + "\n" + new_line + text[end:]
            else:
                new_text = text  # malformed frontmatter — don't touch
        else:
            new_text = "---\n" + new_line + "\n---\n\n" + text
    path.write_text(new_text, encoding="utf-8")
    return True


def find_md_file(directory: str, item_id: str, fallback_paths: list[str] | None = None) -> Path | None:
    """Locate `{item_id}.md` in `directory` or `directory/items/`.
    `fallback_paths` is consulted last (e.g. when the parser already resolved
    the actual file_path)."""
    base = Path(directory)
    for p in (base / f"{item_id}.md", base / "items" / f"{item_id}.md"):
        if p.exists():
            return p
    for fp in (fallback_paths or []):
        p = Path(fp)
        if p.exists():
            return p
    return None
