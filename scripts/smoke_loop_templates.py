"""Smoke check for Wave B loop templates port.

Run: python scripts/smoke_loop_templates.py
Exits 0 on success, non-zero on failure.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dreaming.services.loop_templates import (
    LoopTemplate, list_templates, read_template, write_template, delete_template,
)
from dreaming.services.loop_templates_seed import _SEEDS, seed_if_empty


def smoke_seed_writes_16():
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_lt_"))
    try:
        n = seed_if_empty(str(tmp))
        assert n == 16, f"expected 16 seeds, got {n}"
        # Re-seed: should be idempotent (0 new writes).
        n2 = seed_if_empty(str(tmp))
        assert n2 == 0, f"expected 0 on re-seed, got {n2}"
        # All 16 files exist with .md extension.
        md_files = sorted(tmp.glob("*.md"))
        assert len(md_files) == 16, f"expected 16 .md files, got {len(md_files)}"
        # Each loadable via list_templates.
        loaded = list_templates(str(tmp))
        assert len(loaded) == 16, f"list_templates returned {len(loaded)}"
        # Slugs preserved.
        loaded_slugs = {t.slug for t in loaded}
        seed_slugs = {t.slug for t in _SEEDS}
        assert loaded_slugs == seed_slugs, (
            f"slug mismatch. Missing: {seed_slugs - loaded_slugs}; Extra: {loaded_slugs - seed_slugs}"
        )
        print("  [OK] seed_if_empty writes 16 idempotent templates")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def smoke_crud_cycle():
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_lt_crud_"))
    try:
        tpl = LoopTemplate(
            slug="smoke-test-tpl",
            name="Smoke test template",
            description="Just for smoke",
            engine="loop",
            max_iterations=3,
            tags=["smoke"],
            team="auto",
            body="Hello {{var}}",
        )
        path = write_template(str(tmp), tpl)
        assert path.exists(), "write_template did not create the file"
        loaded = read_template(str(tmp), "smoke-test-tpl")
        assert loaded is not None, "read_template returned None"
        assert loaded.name == "Smoke test template"
        assert loaded.tags == ["smoke"]
        assert loaded.body.strip() == "Hello {{var}}"
        deleted = delete_template(str(tmp), "smoke-test-tpl")
        assert deleted is True
        assert read_template(str(tmp), "smoke-test-tpl") is None
        print("  [OK] write/read/delete cycle")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def smoke_seed_skips_existing():
    """Adding a user-authored template alongside seeds should not be overwritten."""
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_lt_skip_"))
    try:
        user_tpl = LoopTemplate(
            slug="bug-fix-with-tests",  # collides with a seed slug
            name="User's customization",
            body="Custom body",
        )
        write_template(str(tmp), user_tpl)
        # First seed run: should write 15 (skips the user's slug).
        n = seed_if_empty(str(tmp))
        assert n == 15, f"expected 15 seeds (skip 1), got {n}"
        # User's file is unchanged.
        kept = read_template(str(tmp), "bug-fix-with-tests")
        assert kept is not None and kept.name == "User's customization"
        print("  [OK] seed_if_empty skips user-owned slugs")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    smoke_seed_writes_16()
    smoke_crud_cycle()
    smoke_seed_skips_existing()
    print("smoke_loop_templates OK")


if __name__ == "__main__":
    main()
