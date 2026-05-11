"""Starter-kit slash-commands: detect status and install into a project.

The template lives at `<repo>/templates/starter-kit/`. Files under that root are
mirrored into `<working_dir>/.claude/` preserving structure.
"""
from __future__ import annotations
import shutil
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "templates" / "starter-kit"


@dataclass
class StarterKitStatus:
    template_files: list[str]      # relative paths inside template
    installed: list[str]           # subset present in working_dir
    missing: list[str]             # subset absent in working_dir
    all_present: bool
    template_root: str


@dataclass
class InstallResult:
    copied: list[str]
    overwritten: list[str]
    skipped: list[str]
    dry_run: bool


def _template_files() -> list[Path]:
    if not TEMPLATE_DIR.exists():
        return []
    return [p for p in TEMPLATE_DIR.rglob("*") if p.is_file()]


def status(working_dir: str | Path) -> StarterKitStatus:
    wd = Path(working_dir)
    target_base = wd / ".claude"
    files = _template_files()
    rels = [str(p.relative_to(TEMPLATE_DIR)).replace("\\", "/") for p in files]
    installed = [r for r in rels if (target_base / r).exists()]
    missing = [r for r in rels if not (target_base / r).exists()]
    return StarterKitStatus(
        template_files=rels,
        installed=installed,
        missing=missing,
        all_present=(len(missing) == 0 and len(rels) > 0),
        template_root=str(TEMPLATE_DIR),
    )


def install(working_dir: str | Path, *, force: bool = False, dry_run: bool = False) -> InstallResult:
    wd = Path(working_dir)
    if not wd.exists():
        raise FileNotFoundError(f"working_dir does not exist: {wd}")
    target_base = wd / ".claude"
    copied: list[str] = []
    overwritten: list[str] = []
    skipped: list[str] = []
    for src in _template_files():
        rel = str(src.relative_to(TEMPLATE_DIR)).replace("\\", "/")
        dst = target_base / rel
        if dst.exists() and not force:
            skipped.append(rel)
            continue
        existed = dst.exists()
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        (overwritten if existed else copied).append(rel)
    return InstallResult(copied=copied, overwritten=overwritten, skipped=skipped, dry_run=dry_run)
