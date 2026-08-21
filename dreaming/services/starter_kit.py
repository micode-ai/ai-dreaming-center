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
    stale: list[str]               # installed, but content differs from template
    all_present: bool
    up_to_date: bool               # nothing missing AND nothing stale
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


def _normalized(path: Path) -> bytes:
    """File content with line-ending and trailing-newline noise removed.

    An installed copy that differs from the template only in CRLF vs LF is the
    same command, and reporting it as drifted would cry wolf — the one signal
    that has to stay trustworthy is the one that says a session is about to run
    old rules. Compared as bytes rather than decoded text so a file that is not
    valid UTF-8 still compares rather than raising.
    """
    return path.read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n")


def _same_content(template: Path, installed: Path) -> bool:
    try:
        return _normalized(template) == _normalized(installed)
    except OSError:
        # Unreadable either side: not a drift claim we can stand behind.
        return True


def command_stale(working_dir: str | Path, command_name: str) -> bool:
    """Is an *installed* starter-kit command's content behind the template?

    False when the command is absent — that is `command_installed`'s signal,
    and a route that reports both would say two things about one file. False
    too when the template itself is gone, since there is nothing to be behind.

    This exists because the center could see a command missing but never see
    one go stale, so an installed copy silently aged as the templates moved on.
    A real project ran a wave-A `write-article.md` for a day after the question
    channel shipped: the session started, wrote, and simply could not ask —
    a feature absent with no error anywhere to say so.
    """
    installed = Path(working_dir) / ".claude" / "commands" / f"{command_name}.md"
    template = TEMPLATE_DIR / "commands" / f"{command_name}.md"
    if not installed.exists() or not template.exists():
        return False
    return not _same_content(template, installed)


def command_installed(working_dir: str | Path, command_name: str) -> bool:
    """Is a single starter-kit slash-command present in this project's
    .claude/commands/? Cheaper than status(), which walks and diffs the whole
    kit, when a route only needs to know about one file before dispatching it
    (I4) — e.g. `command_installed(wd, "write-article")` checks for
    `.claude/commands/write-article.md`."""
    return (Path(working_dir) / ".claude" / "commands" / f"{command_name}.md").exists()


def status(working_dir: str | Path) -> StarterKitStatus:
    wd = Path(working_dir)
    target_base = wd / ".claude"
    files = _template_files()
    rels = [str(p.relative_to(TEMPLATE_DIR)).replace("\\", "/") for p in files]
    installed = [r for r in rels if (target_base / r).exists()]
    missing = [r for r in rels if not (target_base / r).exists()]
    stale = [
        r for r in installed
        if not _same_content(TEMPLATE_DIR / r, target_base / r)
    ]
    return StarterKitStatus(
        template_files=rels,
        installed=installed,
        missing=missing,
        stale=stale,
        all_present=(len(missing) == 0 and len(rels) > 0),
        up_to_date=(len(missing) == 0 and len(stale) == 0 and len(rels) > 0),
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
