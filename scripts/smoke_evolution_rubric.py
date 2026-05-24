"""Smoke check for Wave D evolution rubric.

Run: python scripts/smoke_evolution_rubric.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dreaming.services.evolution_rubric import (
    collect_stats, parse_rubric_from_file, EvolutionRubric,
)


def _write_evolution(d: Path, slug: str, rubric_block: str | None):
    p = d / f"{slug}.md"
    fm_lines = ["---"]
    if rubric_block:
        fm_lines.append("rubric:")
        for line in rubric_block.strip().split("\n"):
            fm_lines.append("  " + line)
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append("Body")
    p.write_text("\n".join(fm_lines), encoding="utf-8")


def smoke_collect_stats_buckets():
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_rubric_"))
    try:
        # 1 auto: evidence=strong, durability=durable, safety=safe, action=skill
        _write_evolution(tmp, "auto1",
            "evidence_strength: strong\ndurability: durable\nsafety: safe\nrecommended_action: skill\nreusability: cross_agent")
        # 1 review: safety=needs_review forces review verdict (other fields OK)
        _write_evolution(tmp, "review1",
            "evidence_strength: strong\ndurability: durable\nsafety: needs_review\nrecommended_action: skill")
        # 1 reject: safety=unsafe
        _write_evolution(tmp, "reject1",
            "evidence_strength: strong\ndurability: durable\nsafety: unsafe\nrecommended_action: skill")
        # 1 incomplete: missing safety field
        _write_evolution(tmp, "incomplete1",
            "evidence_strength: strong\ndurability: durable\nrecommended_action: skill")
        # 1 with no rubric block at all
        _write_evolution(tmp, "norubric1", None)
        # 1 file with `_` prefix (should be skipped)
        _write_evolution(tmp, "_skipped", "evidence_strength: strong\ndurability: durable\nsafety: safe\nrecommended_action: skill")

        stats = collect_stats(str(tmp))
        assert stats.total == 5, f"expected total=5 (5 non-_ files), got {stats.total}"
        assert stats.with_rubric == 4, f"expected with_rubric=4, got {stats.with_rubric}"
        assert stats.auto == 1, f"expected auto=1, got {stats.auto}"
        assert stats.review == 1, f"expected review=1, got {stats.review}"
        assert stats.reject == 1, f"expected reject=1, got {stats.reject}"
        assert stats.incomplete == 1, f"expected incomplete=1, got {stats.incomplete}"
        print("  [OK] collect_stats verdict distribution")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def smoke_no_rubric_dir_safe():
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_rubric_empty_"))
    try:
        stats = collect_stats(str(tmp))
        assert stats.total == 0 and stats.with_rubric == 0
        # Non-existent dir
        stats2 = collect_stats(str(tmp / "does-not-exist"))
        assert stats2.total == 0
        print("  [OK] collect_stats handles empty/missing dirs")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def smoke_template_parses():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("dreaming/templates"))
    env.filters["t"] = lambda k, **kw: k
    env.get_template("project_evolutions.html")
    print("  [OK] project_evolutions.html parses")


def main():
    smoke_collect_stats_buckets()
    smoke_no_rubric_dir_safe()
    smoke_template_parses()
    print("smoke_evolution_rubric OK")


if __name__ == "__main__":
    main()
