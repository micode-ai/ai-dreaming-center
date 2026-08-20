"""Publish an article by committing exactly its own files.

Hard rules, and the reason for them: orchestration in this repo once swept
uncommitted work out of a project with `git stash -u`, and this feature runs
against eleven working trees that belong to the user, not to us. So:

  * stage only the paths the writer reported, never `git add -A`;
  * never `git stash`, for any reason;
  * if a target path already carries uncommitted edits that are not ours,
    refuse — the user's unsaved work outranks our commit.
"""
from __future__ import annotations
import asyncio
import shutil
import subprocess
from pathlib import Path


class PublishError(RuntimeError):
    """Publishing refused or failed. The message is shown to the user."""


def split_paths(draft_ref: str) -> list[str]:
    """draft_ref may list several paths, comma- or newline-separated."""
    parts = [p.strip() for p in (draft_ref or "").replace("\n", ",").split(",")]
    return [p for p in parts if p]


def build_message(row: dict, label: str) -> str:
    """Commit subject + the verification claim, which must match reality."""
    title = (row.get("title") or "article").strip()
    slug = (row.get("slug_hint") or "").strip()
    head = f"content: publish “{title}”"
    body = [f"slug: {slug}" if slug else "", f"verification: {label}"]
    if row.get("source") and row.get("source_ref"):
        body.append(f"proposed from {row['source']} {row['source_ref']}")
    return head + "\n\n" + "\n".join(b for b in body if b) + "\n"


async def _run(cmd: list[str], cwd: str) -> tuple[int, str, str]:
    """subprocess in a thread: create_subprocess_exec needs a ProactorEventLoop
    on Windows and uvicorn --reload does not always provide one."""
    def _do() -> tuple[int, str, str]:
        try:
            r = subprocess.run(
                cmd, cwd=cwd, capture_output=True, check=False, shell=False,
            )
            return (r.returncode,
                    r.stdout.decode("utf-8", errors="replace"),
                    r.stderr.decode("utf-8", errors="replace"))
        except OSError as e:
            return -1, "", str(e)
    return await asyncio.to_thread(_do)


async def publish(
    working_dir: str, paths: list[str], *, message: str, push: bool,
) -> str:
    """Stage `paths`, commit, optionally push. Returns the new commit sha."""
    if not paths:
        raise PublishError("nothing to publish: the draft reported no paths")
    wd = Path(working_dir)
    if not (wd / ".git").exists():
        raise PublishError(f"{working_dir} is not a git repository")
    git = shutil.which("git") or "git"

    # Refuse when a target path holds edits that are not the draft itself.
    # `git status --porcelain -- <paths>` lists staged and unstaged changes; an
    # index entry we did not create means someone else is mid-edit here.
    rc, out, err = await _run([git, "status", "--porcelain", "--", *paths], str(wd))
    if rc != 0:
        raise PublishError(f"git status failed: {err.strip() or rc}")
    staged = [ln for ln in out.splitlines() if ln[:1] not in (" ", "?", "")]
    if staged:
        raise PublishError(
            "these paths already have staged changes — commit or reset them "
            "first:\n" + "\n".join(staged)
        )

    rc, _out, err = await _run([git, "add", "--", *paths], str(wd))
    if rc != 0:
        raise PublishError(f"git add failed: {err.strip() or rc}")

    rc, out, err = await _run(
        [git, "diff", "--cached", "--name-only"], str(wd),
    )
    if rc != 0:
        raise PublishError(f"git diff --cached failed: {err.strip() or rc}")
    if not out.strip():
        raise PublishError("nothing staged: the draft paths match HEAD already")

    rc, out, err = await _run([git, "commit", "-m", message], str(wd))
    if rc != 0:
        raise PublishError(f"git commit failed: {(err or out).strip() or rc}")

    rc, sha, err = await _run([git, "rev-parse", "HEAD"], str(wd))
    if rc != 0:
        raise PublishError(f"git rev-parse failed: {err.strip() or rc}")
    commit = sha.strip()

    if push:
        rc, out, err = await _run([git, "push"], str(wd))
        if rc != 0:
            raise PublishError(
                f"committed {commit[:8]} but the push failed: "
                f"{(err or out).strip() or rc}"
            )
    return commit
