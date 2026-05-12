"""Thin async client for GitHub Issues via the `gh` CLI.

Auth comes from the user's existing `gh auth login` session — no extra token
configuration in DC. The target repository is resolved in this order:

  1. explicit `repo_override` argument (`owner/name`)
  2. per-project `github_repo` setting (`owner/name`)
  3. `git remote get-url origin` of the project's working_dir

Used by the "Send to GitHub" button on Findings and Ideas detail / list pages.
"""
from __future__ import annotations
import asyncio
import logging
import re
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


class GitHubIssueError(RuntimeError):
    """User-facing GitHub failure — message is safe to show in the UI."""


_GH_URL_RE = re.compile(r"github\.com[:/]([^/]+)/([^/.\s]+)")


async def _git_remote_repo(working_dir: str) -> str | None:
    """Return `owner/name` parsed from `git remote get-url origin`, or None."""
    if not Path(working_dir).exists():
        return None
    git = shutil.which("git") or "git"
    try:
        proc = await asyncio.create_subprocess_exec(
            git, "-C", working_dir, "remote", "get-url", "origin",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
    except OSError as e:
        log.warning("git remote lookup failed: %s", e)
        return None
    if proc.returncode != 0:
        return None
    url = stdout.decode("utf-8", errors="replace").strip()
    m = _GH_URL_RE.search(url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


async def resolve_repo(working_dir: str, override: str | None = None) -> str:
    if override:
        return override
    repo = await _git_remote_repo(working_dir)
    if repo is None:
        raise GitHubIssueError(
            "Не удалось определить GitHub-репозиторий: ни override, ни "
            "git remote origin не указывают на github.com. Пропиши "
            "`github_repo` в Settings (формат `owner/name`)."
        )
    return repo


# Stable color palette for the labels DC creates on first use.
_LABEL_DEFAULTS: dict[str, tuple[str, str]] = {
    "tech-debt":     ("d93f0b", "Tech-debt item surfaced by AI Dreaming Center"),
    "product-idea":  ("1d76db", "Product idea surfaced by AI Dreaming Center"),
    "priority:p1":   ("b60205", "Priority: high"),
    "priority:p2":   ("fbca04", "Priority: normal"),
    "priority:p3":   ("0e8a16", "Priority: nice-to-have"),
}


async def _ensure_label(gh: str, repo: str, name: str) -> None:
    """Best-effort: create a label in the repo if it doesn't already exist.
    Ignores 'already exists' errors. Logs and swallows everything else so the
    caller can still try the issue create."""
    color, description = _LABEL_DEFAULTS.get(name, ("ededed", ""))
    cmd = [gh, "label", "create", name, "--repo", repo, "--color", color]
    if description:
        cmd += ["--description", description]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            msg = stderr.decode("utf-8", errors="replace").lower()
            # 'already_exists' is fine; anything else is just a warning.
            if "already_exists" in msg or "already exists" in msg:
                return
            log.warning("gh label create %s in %s: %s", name, repo, msg.strip()[:200])
    except OSError as e:
        log.warning("gh label create OSError for %s: %s", name, e)


async def create_issue(
    *,
    working_dir: str,
    repo_override: str | None = None,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
) -> dict:
    """Create a GitHub issue. Returns `{'url': str, 'number': int, 'repo': str}`.

    Raises GitHubIssueError on any failure.
    """
    repo = await resolve_repo(working_dir, repo_override)
    gh = shutil.which("gh") or "gh"

    # Pre-create any requested labels (idempotent). If something goes wrong
    # here we still try the issue-create — labels are nice-to-have.
    for lab in (labels or []):
        await _ensure_label(gh, repo, lab)

    async def _try_create(with_labels: list[str]) -> tuple[int, bytes, bytes]:
        c = [gh, "issue", "create", "--repo", repo, "--title", title,
             "--body", body or "(no body — created by AI Dreaming Center)"]
        for lab in with_labels:
            c += ["--label", lab]
        try:
            proc = await asyncio.create_subprocess_exec(
                *c, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout, stderr
        except OSError as e:
            raise GitHubIssueError(f"Не удалось вызвать gh CLI: {e}") from None

    rc, stdout, stderr = await _try_create(labels or [])
    if rc != 0:
        msg = stderr.decode("utf-8", errors="replace").strip()
        msg_l = msg.lower()
        # Retry without labels if the failure is label-related (e.g. token
        # lacks scope to create labels in this org).
        if ("could not add label" in msg_l or "could not find label" in msg_l) and labels:
            log.warning("retrying gh issue create without labels: %s", msg[:200])
            rc, stdout, stderr = await _try_create([])
        if rc != 0:
            msg = stderr.decode("utf-8", errors="replace").strip() or "(no stderr)"
            if "not logged into" in msg.lower():
                raise GitHubIssueError("gh CLI не залогинен — выполни `gh auth login`")
            raise GitHubIssueError(f"gh issue create failed: {msg}")

    url = stdout.decode("utf-8", errors="replace").strip().splitlines()[-1]
    m = re.search(r"/issues/(\d+)$", url)
    number = int(m.group(1)) if m else 0
    log.info("Created GitHub issue %s for repo %s", url, repo)
    return {"url": url, "number": number, "repo": repo}
