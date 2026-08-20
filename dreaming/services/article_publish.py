"""Publish an article by committing exactly its own files.

Hard rules, and the reason for them: orchestration in this repo once swept
uncommitted work out of a project with `git stash -u`, and this feature runs
against eleven working trees that belong to the user, not to us. So:

  * stage only the paths the writer reported, never `git add -A`;
  * commit only those same paths, never the whole index — `git commit` with
    no pathspec commits everything currently staged, so if the user had
    something else staged elsewhere in the repo, an unscoped commit would
    silently sweep it into ours. Fixed 2026-08-20 after a review proved this
    with a throwaway repo: an unrelated staged file rode along into a
    "content: publish ..." commit. The commit call now passes `-- <paths>`,
    same as `add`;
  * never `git stash`, for any reason;
  * if a target path already carries uncommitted edits that are not ours,
    refuse — the user's unsaved work outranks our commit.

`draft_ref` arrives over HTTP from a writer session and reaches git as a
pathspec, not a plain filename. Git's pathspec syntax is far richer than a
literal path: a `..` segment that stays inside the repo is a valid pathspec,
`*`/`?`/`[]` are glob magic, and a leading `:` opens `:(...)` magic — any of
these can turn "stage this one file" into the equivalent of `git add -A`,
which is the one thing this module exists to refuse. `_validate_paths`
rejects all of that before git ever sees the string, and `--literal-pathspecs`
on the git calls themselves is the belt-and-suspenders backstop in case
something slips past the character checks.
"""
from __future__ import annotations
import asyncio
import re
import shutil
import subprocess
from pathlib import Path, PurePath


class PublishError(RuntimeError):
    """Publishing refused or failed. The message is shown to the user."""


class PushFailed(PublishError):
    """The commit landed locally but `git push` failed.

    Distinct from PublishError so the caller can still record the commit —
    treating this like any other PublishError would drop the sha on the
    floor and leave the row stuck: a retry would find the draft paths
    already matching HEAD (the commit happened) and refuse with "nothing to
    publish" forever, and a human would have no `commit_ref` to push by hand.
    """

    def __init__(self, message: str, *, commit: str, output: str):
        super().__init__(message)
        self.commit = commit
        self.output = output


_PATHSPEC_MAGIC_CHARS = set("*?[]")
_DRIVE_RE = re.compile(r"^[a-zA-Z]:[\\/]?")


def _validate_paths(paths: list[str], repo_root: Path) -> None:
    """Refuse anything that is not a plain, in-repo, existing regular file.

    repo_root must already be resolved (no symlinks/`..` left in it) so the
    containment check below is meaningful.
    """
    for p in paths:
        if p.startswith(":"):
            raise PublishError(
                f"invalid path (pathspec magic not allowed): {p!r}"
            )
        if any(ch in p for ch in _PATHSPEC_MAGIC_CHARS):
            raise PublishError(
                f"invalid path (glob characters not allowed): {p!r}"
            )
        if p.startswith(("/", "\\")) or _DRIVE_RE.match(p) or PurePath(p).is_absolute():
            raise PublishError(
                f"invalid path (absolute paths not allowed): {p!r}"
            )
        if ".." in re.split(r"[\\/]+", p):
            raise PublishError(
                f"invalid path (contains a '..' segment): {p!r}"
            )
        resolved = (repo_root / p).resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            raise PublishError(
                f"invalid path (escapes the repository): {p!r}"
            )
        if not resolved.exists():
            raise PublishError(f"invalid path (does not exist): {p!r}")
        if not resolved.is_file():
            raise PublishError(f"invalid path (not a regular file): {p!r}")


def split_paths(draft_ref: str, working_dir: str = "") -> list[str]:
    """draft_ref may list several paths, comma- or newline-separated.

    A comma is also legal inside a real filename, so a whole-string match
    against the filesystem wins first: if the trimmed string as-is names an
    existing file under `working_dir`, that is the answer, commas and all.
    Only when it does not resolve do we fall back to splitting — so a
    genuinely broken value fails safe (via `_validate_paths` in `publish`)
    instead of the comma silently chopping a directory into scope.
    """
    whole = (draft_ref or "").strip()
    if whole and working_dir and (Path(working_dir) / whole).is_file():
        return [whole]
    parts = [p.strip() for p in whole.replace("\n", ",").split(",")]
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

    _validate_paths(paths, wd.resolve())

    # Refuse when a target path holds edits that are not the draft itself.
    # `git status --porcelain -- <paths>` lists staged and unstaged changes; an
    # index entry we did not create means someone else is mid-edit here.
    # --literal-pathspecs is belt-and-suspenders: _validate_paths above already
    # rejects pathspec magic, but this stops it from being honoured even if
    # something slipped past those checks.
    rc, out, err = await _run(
        [git, "--literal-pathspecs", "status", "--porcelain", "--", *paths],
        str(wd),
    )
    if rc != 0:
        raise PublishError(f"git status failed: {err.strip() or rc}")
    staged = [ln for ln in out.splitlines() if ln[:1] not in (" ", "?", "")]
    if staged:
        raise PublishError(
            "these paths already have staged changes — commit or reset them "
            "first:\n" + "\n".join(staged)
        )

    # Never -f/--force: git's refusal to add a gitignored file without it is
    # load-bearing, it is what keeps a gitignored secret out of our commits.
    rc, _out, err = await _run(
        [git, "--literal-pathspecs", "add", "--", *paths], str(wd),
    )
    if rc != 0:
        raise PublishError(f"git add failed: {err.strip() or rc}")

    rc, out, err = await _run(
        [git, "diff", "--cached", "--name-only"], str(wd),
    )
    if rc != 0:
        raise PublishError(f"git diff --cached failed: {err.strip() or rc}")
    if not out.strip():
        raise PublishError("nothing staged: the draft paths match HEAD already")

    # Scoped to `-- *paths`, same as `add` above: a bare `git commit` commits
    # the *entire* index, so if the user had anything else staged elsewhere
    # in the repo, it would ride along into our commit under our message.
    # The pathspec form only commits the index entries matching these paths
    # and leaves every other staged entry exactly as the user left it.
    rc, out, err = await _run(
        [git, "--literal-pathspecs", "commit", "-m", message, "--", *paths],
        str(wd),
    )
    if rc != 0:
        # The paths are still staged in the user's index. Left alone, a retry
        # would see our own leftovers at the pre-check above -- indistinguishable
        # by design from a human's staged work -- and refuse forever. The reset
        # is safe here specifically because the pre-check above refused unless
        # these paths were clean, so nothing but our own `git add` is undone.
        # But the reset itself can fail too (lock file, permissions) -- check
        # its own return code rather than asserting a rollback that may not
        # have happened.
        reset_rc, reset_out, reset_err = await _run(
            [git, "--literal-pathspecs", "reset", "-q", "--", *paths], str(wd),
        )
        commit_detail = (err or out).strip() or str(rc)
        if reset_rc == 0:
            raise PublishError(
                f"git commit failed (staged changes rolled back): {commit_detail}"
            )
        raise PublishError(
            f"git commit failed: {commit_detail}\n"
            "the staging could not be rolled back -- these paths are still "
            f"staged, run `git reset -- <path>` yourself for: "
            f"{', '.join(paths)}\n"
            f"reset error: {(reset_err or reset_out).strip() or str(reset_rc)}"
        )

    rc, sha, err = await _run([git, "rev-parse", "HEAD"], str(wd))
    if rc != 0:
        # The commit already landed -- resetting the index now would be a
        # content no-op, not a rollback, and claiming one would be false. The
        # sha is unknown, so a retry will (correctly) refuse with "nothing
        # staged: the draft paths match HEAD already"; say why up front.
        raise PublishError(
            "git commit succeeded but its sha could not be read; nothing was "
            "rolled back -- the commit is already in the project's history, "
            f"find it with `git log`: {err.strip() or str(rc)}"
        )
    commit = sha.strip()

    if push:
        rc, out, err = await _run([git, "push"], str(wd))
        if rc != 0:
            raise PushFailed(
                f"committed {commit[:8]} but the push failed: "
                f"{(err or out).strip() or rc}",
                commit=commit, output=(err or out).strip(),
            )
    return commit
