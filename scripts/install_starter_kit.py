"""Copy starter-kit slash-commands into a project's .claude/commands/.

Usage:
    python scripts/install_starter_kit.py --slug <project-slug>
    python scripts/install_starter_kit.py --working-dir <path>
    python scripts/install_starter_kit.py --all                # all enabled projects in DB
    python scripts/install_starter_kit.py --slug foo --force   # overwrite existing
    python scripts/install_starter_kit.py --slug foo --dry-run

`--slug` and `--all` read the projects table from data/dreaming.db (override
with --db-path). `--working-dir` skips the DB entirely.
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dreaming.services.starter_kit import install, InstallResult  # noqa: E402


def _print_result(label: str, r: InstallResult) -> None:
    tag = " (dry-run)" if r.dry_run else ""
    print(f"  {label}{tag}: {len(r.copied)} new, {len(r.overwritten)} overwritten, {len(r.skipped)} skipped")
    for f in r.copied:
        print(f"    copy        {f}")
    for f in r.overwritten:
        print(f"    overwrite   {f}")
    for f in r.skipped:
        print(f"    skip        {f}  (exists; use --force to overwrite)")


def _resolve_working_dir(slug: str, db_path: Path) -> Path:
    if not db_path.exists():
        sys.exit(f"DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT working_dir FROM projects WHERE slug=?", (slug,)).fetchone()
    finally:
        conn.close()
    if row is None:
        sys.exit(f"no project with slug '{slug}' in {db_path}")
    return Path(row[0])


def _all_enabled(db_path: Path) -> list[tuple[str, Path]]:
    if not db_path.exists():
        sys.exit(f"DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT slug, working_dir FROM projects WHERE enabled=1 ORDER BY sort_order, slug"
        ).fetchall()
    finally:
        conn.close()
    return [(slug, Path(wd)) for slug, wd in rows]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="project slug (looked up in DB)")
    group.add_argument("--working-dir", help="direct path to project working_dir")
    group.add_argument("--all", action="store_true", help="install into every enabled project")
    p.add_argument("--db-path", default=str(REPO_ROOT / "data" / "dreaming.db"))
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.add_argument("--dry-run", action="store_true", help="print what would happen, don't write")
    args = p.parse_args()

    db_path = Path(args.db_path).resolve()

    if args.working_dir:
        wd = Path(args.working_dir).resolve()
        print(f"-> {wd}")
        _print_result(str(wd), install(wd, force=args.force, dry_run=args.dry_run))
    elif args.slug:
        wd = _resolve_working_dir(args.slug, db_path).resolve()
        print(f"-> '{args.slug}' at {wd}")
        _print_result(args.slug, install(wd, force=args.force, dry_run=args.dry_run))
    else:
        targets = _all_enabled(db_path)
        if not targets:
            sys.exit("no enabled projects in DB")
        for slug, wd in targets:
            wd = wd.resolve()
            print(f"\n-> '{slug}' at {wd}")
            _print_result(slug, install(wd, force=args.force, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
