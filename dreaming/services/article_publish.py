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

`plan_rollback` / `rollback` at the bottom are the same story in reverse --
taking a draft back out of a working tree the operator decided against. They
obey every rule above, for the same reason: undoing our own write must not be
able to touch anything the writer did not report.
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


def _find_nested_git(tree: Path) -> Path | None:
    """First `.git` entry (file or directory) found anywhere inside `tree`,
    or None.

    `git add` on a directory containing its own `.git` stages a `160000`
    gitlink — a bare commit reference with none of the actual files, no
    `.gitmodules` to resolve it, and `git add`'s own return code is 0, so
    nothing about the add call itself catches it. Realistic for a build
    output that vendored a themed asset by cloning it. Checked once per
    extra path, at validation time, so it is refused before any git call —
    no rollback is needed for a refusal that never staged anything.
    """
    if tree.is_file():
        return None
    for entry in tree.rglob(".git"):
        return entry
    return None


def _validate_paths(
    paths: list[str], repo_root: Path, *, allow_dirs: bool = False,
    require_exists: bool = True,
) -> None:
    """Refuse anything that is not a plain, in-repo, existing path.

    repo_root must already be resolved (no symlinks/`..` left in it) so the
    containment check below is meaningful.

    By default (`allow_dirs=False`) an existing *directory* is refused too —
    this is the mode for `draft_ref`, a value self-reported by a Claude
    session over unauthenticated localhost HTTP; a directory there would let
    one report stage a whole subtree. `allow_dirs=True` widens exactly that
    one check to also accept a directory — the mode for
    `article_publish_extra_paths`, which an operator types into project
    settings rather than a session reporting it, and where a build's output
    legitimately is a subtree. Every other rule (no absolute paths, no `..`,
    no glob characters, containment, existence, no nested `.git`) applies
    identically to both, so the two modes cannot drift on those.

    `require_exists=False` drops only the existence check, for
    `plan_rollback`: a draft_ref path whose file is already gone is nothing
    left to roll back, and refusing the whole discard over it would strand
    the operator with a row they cannot close. Every hostile-string rule
    still applies -- that is why this is a parameter here rather than a
    second validator somewhere else.
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
            if require_exists:
                raise PublishError(f"invalid path (does not exist): {p!r}")
            continue
        if not allow_dirs and not resolved.is_file():
            raise PublishError(f"invalid path (not a regular file): {p!r}")
        if allow_dirs and resolved.is_dir():
            nested = _find_nested_git(resolved)
            if nested is not None:
                raise PublishError(
                    "invalid path (contains a nested .git, would stage a "
                    f"dangling gitlink instead of files): "
                    f"{nested.relative_to(repo_root)}"
                )


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


async def _rollback_or_raise(
    git: str, wd: Path, rollback_paths: list[str], *, step: str, detail: str,
) -> None:
    """A staging step (`git add` for either group, or `git commit`) failed.

    Attempt `git reset -q --literal-pathspecs -- <rollback_paths>` to unstage
    whatever that step (and any step before it in this same publish call)
    may have left in the index, then raise `PublishError` with an honest
    account of the outcome: reset succeeded (say so), or reset itself also
    failed (name exactly what is still staged, so a human can clear it —
    this is someone else's repository, not ours to leave dirty and silent
    about it).

    `rollback_paths` should be the full set touched so far this call — safe
    even for paths that were never actually staged, since resetting a path
    that is not in the index is a no-op.

    Shared by every failure that can leave a partial stage behind, so the
    disclosure — and the fact that reset's own return code is checked
    rather than assumed — cannot drift between them.
    """
    reset_rc, reset_out, reset_err = await _run(
        [git, "--literal-pathspecs", "reset", "-q", "--", *rollback_paths], str(wd),
    )
    if reset_rc == 0:
        raise PublishError(f"{step} failed (staged changes rolled back): {detail}")
    raise PublishError(
        f"{step} failed: {detail}\n"
        "the staging could not be rolled back -- these paths are still "
        f"staged, run `git reset -- <path>` yourself for: "
        f"{', '.join(rollback_paths)}\n"
        f"reset error: {(reset_err or reset_out).strip() or str(reset_rc)}"
    )


def validate_draft_paths(paths: list[str], working_dir: str) -> None:
    """The draft_ref check `publish` runs, callable before publish time.

    Recording a draft by hand takes the paths from a form instead of from a
    writer session, and a typo there must be refused while the operator is
    still looking at the field — not saved and then re-discovered as a failed
    publish on a row that already claims to hold a draft. Same rules and the
    same messages as publish, deliberately: two ways of describing the same
    string would eventually disagree.
    """
    _validate_paths(paths, Path(working_dir).resolve())


async def publish(
    working_dir: str, paths: list[str], *, message: str, push: bool,
    extra_paths: list[str] | None = None,
) -> str:
    """Stage `paths` and any `extra_paths`, commit, optionally push.

    `paths` is `draft_ref`, split — the writer's own self-reported files,
    validated as plain existing files only (`_validate_paths`, default
    mode). `extra_paths` is `article_publish_extra_paths`, an operator-typed
    setting: it may also name directories, since a build's output is a
    subtree, but every other validation rule still applies. Both groups are
    staged (one `git add` per group) and committed together, scoped to their
    union, so the wave A guarantee — nothing outside the reported/configured
    paths is ever touched — holds for the combined set exactly as it held
    for `paths` alone. Returns the new commit sha.
    """
    extra_paths = extra_paths or []
    if not paths:
        raise PublishError("nothing to publish: the draft reported no paths")
    wd = Path(working_dir)
    if not (wd / ".git").exists():
        raise PublishError(f"{working_dir} is not a git repository")
    git = shutil.which("git") or "git"

    _validate_paths(paths, wd.resolve())
    _validate_paths(extra_paths, wd.resolve(), allow_dirs=True)

    all_paths = paths + extra_paths

    # Refuse when a target path holds edits that are not the draft itself.
    # `git status --porcelain -- <paths>` lists staged and unstaged changes; an
    # index entry we did not create means someone else is mid-edit here.
    # --literal-pathspecs is belt-and-suspenders: _validate_paths above already
    # rejects pathspec magic, but this stops it from being honoured even if
    # something slipped past those checks.
    rc, out, err = await _run(
        [git, "--literal-pathspecs", "status", "--porcelain", "--", *all_paths],
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
    # One `git add` per group (draft_ref, then extra_paths) so a failure
    # names which group it came from, even though both land in one commit.
    #
    # Neither call is atomic across its own pathspecs, and the second call
    # runs against an index the first has already mutated: `git add -- a b`
    # can return non-zero (e.g. `b` is gitignored) while still staging `a`.
    # Left alone that leaves the draft (or a partial extra_paths tree)
    # staged in the caller's repository with no rollback and no mention of
    # it in the raised error — a real reproduction, not a hypothetical: a
    # gitignored build output triggers it directly. `_rollback_or_raise`
    # unstages everything this call (and, for the second call, the first
    # one too) may have touched and says plainly whether that worked.
    rc, _out, err = await _run(
        [git, "--literal-pathspecs", "add", "--", *paths], str(wd),
    )
    if rc != 0:
        await _rollback_or_raise(
            git, wd, all_paths, step="git add", detail=err.strip() or str(rc),
        )
    if extra_paths:
        rc, _out, err = await _run(
            [git, "--literal-pathspecs", "add", "--", *extra_paths], str(wd),
        )
        if rc != 0:
            await _rollback_or_raise(
                git, wd, all_paths, step="git add",
                detail=err.strip() or str(rc),
            )

    rc, out, err = await _run(
        [git, "diff", "--cached", "--name-only"], str(wd),
    )
    if rc != 0:
        raise PublishError(f"git diff --cached failed: {err.strip() or rc}")
    if not out.strip():
        raise PublishError("nothing staged: the draft paths match HEAD already")

    # Nothing staged from extra_paths alone is not an error — the build may
    # have changed nothing, and the check above already confirmed something
    # (from either group) was staged. When extra_paths did stage something,
    # count it and add one line to the commit message naming it, so the
    # diff's size is explained rather than surprising.
    if extra_paths:
        rc, extra_out, err = await _run(
            [git, "--literal-pathspecs", "diff", "--cached", "--name-only",
             "--", *extra_paths],
            str(wd),
        )
        if rc != 0:
            raise PublishError(f"git diff --cached failed: {err.strip() or rc}")
        extra_count = len([ln for ln in extra_out.splitlines() if ln.strip()])
        if extra_count:
            noun = "file" if extra_count == 1 else "files"
            message = (
                message.rstrip("\n")
                + f"\nbuild: {extra_count} {noun} from article_publish_extra_paths\n"
            )

    # Scoped to `-- *all_paths`, same as `add` above: a bare `git commit` commits
    # the *entire* index, so if the user had anything else staged elsewhere
    # in the repo, it would ride along into our commit under our message.
    # The pathspec form only commits the index entries matching these paths
    # and leaves every other staged entry exactly as the user left it.
    rc, out, err = await _run(
        [git, "--literal-pathspecs", "commit", "-m", message, "--", *all_paths],
        str(wd),
    )
    if rc != 0:
        # The paths are still staged in the user's index. Left alone, a retry
        # would see our own leftovers at the pre-check above -- indistinguishable
        # by design from a human's staged work -- and refuse forever. The reset
        # is safe here specifically because the pre-check above refused unless
        # these paths were clean, so nothing but our own `git add` is undone.
        # `_rollback_or_raise` checks the reset's own return code rather than
        # assuming a rollback that may not have happened (lock file,
        # permissions) -- same helper the two `git add` failures above use.
        await _rollback_or_raise(
            git, wd, all_paths, step="git commit",
            detail=(err or out).strip() or str(rc),
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


# ── Rollback: taking a rejected draft back out of the tree ────────────

def _norm_path(p: str) -> str:
    """Slash-separated, no leading/trailing separator — how git names files."""
    return p.replace("\\", "/").strip("/")


def _porcelain_states(out: str) -> dict[str, str]:
    """{path: XY} from `git status --porcelain`.

    A rename reads `XY old -> new`; the new name is the one on disk, so that
    is what we key on. A path git chose to C-quote (unusual bytes in the
    name) will not match its plain form and so falls through to `skip` —
    the safe direction: an unrecognised file is left on disk rather than
    deleted on a guess.
    """
    states: dict[str, str] = {}
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, rest = line[:2], line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        states[_norm_path(rest.strip().strip('"'))] = code
    return states


async def plan_rollback(paths: list[str], working_dir: str) -> list[dict]:
    """What discarding this draft would do to each of its files.

    Four outcomes, decided by one `git status --porcelain` over exactly the
    reported paths:

      * `delete`   — untracked (`??`). The writer created it; it goes.
      * `unstage`  — staged as new (`A` in the index). A publish that died
                     between `git add` and `git commit` leaves this behind,
                     and deleting the file alone would leave the index
                     holding a path that no longer exists.
      * `restore`  — tracked and changed some other way. The writer edited a
                     file that already existed (`src/data/blog-posts.json` and
                     friends), so the file goes back to HEAD rather than away.
      * `skip`     — git reports nothing for it, or it is already gone.

    Read this before acting on it: `restore` takes the whole file back to
    HEAD, so an unrelated edit sitting in the same file is lost with ours.
    That is why the route renders this plan and asks, instead of just doing
    it.

    Returns one dict per input path, in input order, with `path`, `action`
    and the raw two-letter `status` git reported (empty when it reported
    none).
    """
    wd = Path(working_dir).resolve()
    if not (wd / ".git").exists():
        raise PublishError(f"{working_dir} is not a git repository")
    if not paths:
        return []
    _validate_paths(paths, wd, require_exists=False)
    git = shutil.which("git") or "git"
    rc, out, err = await _run(
        [git, "--literal-pathspecs", "status", "--porcelain", "--", *paths],
        str(wd),
    )
    if rc != 0:
        raise PublishError(f"git status failed: {err.strip() or rc}")
    states = _porcelain_states(out)
    plan: list[dict] = []
    for p in paths:
        code = states.get(_norm_path(p), "")
        if code == "??":
            action = "delete"
        elif code[:1] == "A":
            action = "unstage"
        elif code:
            action = "restore"
        else:
            action = "skip"
        plan.append({"path": p, "action": action, "status": code})
    return plan


async def rollback(paths: list[str], working_dir: str) -> list[dict]:
    """Execute `plan_rollback`. Returns the plan it carried out.

    `restore` and `unstage` both `git reset` the path first: without it,
    `git checkout -- <path>` would restore from the index rather than from
    HEAD, quietly reinstating a staged copy of the very draft being
    discarded. Reset on an unstaged path is a no-op, so one order serves
    both.

    A step that fails stops the run and raises, naming what was already
    undone and what was not — half a rollback in someone else's repository
    is exactly the kind of thing that must not be reported as success.
    """
    plan = await plan_rollback(paths, working_dir)
    wd = Path(working_dir).resolve()
    git = shutil.which("git") or "git"
    done: list[str] = []

    def _fail(step: str, detail: str) -> None:
        undone = ", ".join(done) or "nothing"
        raise PublishError(
            f"{step} failed: {detail}\n"
            f"rolled back so far: {undone}; the remaining paths were left "
            "untouched, so the working tree is part-way between the draft "
            "and HEAD -- finish by hand before reusing this row."
        )

    for item in plan:
        action, rel = item["action"], item["path"]
        if action == "skip":
            continue
        if action in ("unstage", "restore"):
            rc, out, err = await _run(
                [git, "--literal-pathspecs", "reset", "-q", "--", rel], str(wd),
            )
            if rc != 0:
                _fail(f"git reset -- {rel}", (err or out).strip() or str(rc))
        if action == "restore":
            rc, out, err = await _run(
                [git, "--literal-pathspecs", "checkout", "-q", "--", rel],
                str(wd),
            )
            if rc != 0:
                _fail(f"git checkout -- {rel}", (err or out).strip() or str(rc))
        else:
            try:
                (wd / rel).unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                _fail(f"delete {rel}", str(e))
        done.append(rel)
    return plan
