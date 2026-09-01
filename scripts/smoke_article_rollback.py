"""Smoke: rolling a drafted article's files back out of a working tree.

Exercises `article_publish.plan_rollback` / `rollback` against a real git
repository, because the whole point of the feature is what git reports:
a file the writer created is deleted, a file it edited goes back to HEAD,
and a file it never touched is left alone.

Run manually:  python scripts/smoke_article_rollback.py
"""
from __future__ import annotations
import asyncio
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services import article_publish as ap  # noqa: E402
from dreaming.services.db import SqliteDB  # noqa: E402

failures: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}: got={got!r} want={want!r}")
    if not ok:
        failures.append(label)


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-c", "user.email=s@x", "-c", "user.name=smoke", *args],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return r.stdout


def make_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dc-smoke-rollback-"))
    git(repo, "init", "-q")
    (repo / "data").mkdir()
    (repo / "data" / "posts.json").write_text("original\n", encoding="utf-8")
    (repo / "data" / "untouched.ts").write_text("untouched\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    return repo


def actions(plan: list[dict]) -> dict[str, str]:
    return {p["path"]: p["action"] for p in plan}


async def main() -> int:
    repo = make_repo()
    root = str(repo)

    # The writer's three kinds of touch: a brand new file, an edit to a
    # tracked one, and a path it listed but left exactly as it found it.
    (repo / "content").mkdir()
    (repo / "content" / "new.md").write_text("draft body\n", encoding="utf-8")
    (repo / "data" / "posts.json").write_text("original\nadded\n", encoding="utf-8")
    paths = ["content/new.md", "data/posts.json", "data/untouched.ts"]

    plan = await ap.plan_rollback(paths, root)
    check("plan: new file is deleted", actions(plan)["content/new.md"], "delete")
    check("plan: edited file is restored", actions(plan)["data/posts.json"], "restore")
    check("plan: untouched file is skipped", actions(plan)["data/untouched.ts"], "skip")

    done = await ap.rollback(paths, root)
    check("rollback reports every path", len(done), 3)
    check("new file is gone", (repo / "content" / "new.md").exists(), False)
    check("edited file is back at HEAD",
          (repo / "data" / "posts.json").read_text(encoding="utf-8"), "original\n")
    check("untouched file still there",
          (repo / "data" / "untouched.ts").read_text(encoding="utf-8"), "untouched\n")
    check("tree is clean again", git(repo, "status", "--porcelain").strip(), "")

    # A publish that died between `git add` and `git commit` leaves the new
    # file staged; deleting it from disk alone would leave it in the index.
    (repo / "content" / "staged.md").write_text("staged draft\n", encoding="utf-8")
    git(repo, "add", "content/staged.md")
    plan = await ap.plan_rollback(["content/staged.md"], root)
    check("plan: staged-new file is unstaged and deleted",
          actions(plan)["content/staged.md"], "unstage")
    await ap.rollback(["content/staged.md"], root)
    check("staged file is gone", (repo / "content" / "staged.md").exists(), False)
    check("index is clean after unstage",
          git(repo, "status", "--porcelain").strip(), "")

    # A path recorded for a file that no longer exists must not crash the
    # panel -- there is simply nothing left to roll back.
    plan = await ap.plan_rollback(["content/vanished.md"], root)
    check("plan: missing file is skipped",
          actions(plan)["content/vanished.md"], "skip")

    # Pathspec magic is refused before git is ever called -- same rules as
    # publish, since this reaches git as a pathspec too.
    for bad in ("../outside.md", "content/*.md", ":(glob)content/**"):
        try:
            await ap.plan_rollback([bad], root)
            check(f"refuses {bad!r}", "accepted", "PublishError")
        except ap.PublishError:
            check(f"refuses {bad!r}", "PublishError", "PublishError")

    await check_mark_published()

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


async def check_mark_published() -> None:
    """The 'already published' button's write side.

    It is the one transition that lands a row in 'published' without a commit
    of ours, so what it must NOT do matters as much as what it does: no
    commit_ref invented, and no row dragged out of a status the button is not
    offered from.
    """
    tmp = Path(tempfile.mkdtemp(prefix="dc-smoke-markpub-")) / "dreaming.db"
    db = SqliteDB(str(tmp))
    await db.connect()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO projects (id, slug, label, working_dir, enabled, "
        " created_at, updated_at) VALUES (1, 'p', 'P', '.', 1, ?, ?)",
        (now, now))

    seq = 0

    async def make(status: str, commit_ref: str = "") -> int:
        # slug_hint is UNIQUE per project -- every fixture row needs its own.
        nonlocal seq
        seq += 1
        await db.execute(
            "INSERT INTO article_proposals (project_id, source, evidence, "
            " title, slug_hint, status, commit_ref, created_at) "
            "VALUES (1, 'smoke', 'e', 't', ?, ?, ?, ?)",
            (f"smoke-{seq}", status, commit_ref, now))
        row = await db.fetch_one("SELECT MAX(id) AS id FROM article_proposals")
        return int(row["id"])

    async def get(pid: int) -> dict:
        return dict(await db.fetch_one(
            "SELECT status, published_at, decided_at, commit_ref "
            "FROM article_proposals WHERE id=?", (pid,)))

    try:
        await _mark_published_checks(db, make, get)
    finally:
        await db.close()


async def _mark_published_checks(db, make, get) -> None:
    for status in ("drafted", "proposed", "failed"):
        pid = await make(status)
        check(f"mark-published accepts {status}",
              await db.mark_article_published_by_hand(pid), True)
        row = await get(pid)
        check(f"{status} -> published", row["status"], "published")
        check(f"{status} stamps published_at", bool(row["published_at"]), True)
        check(f"{status} fills decided_at", bool(row["decided_at"]), True)
        check(f"{status} invents no commit_ref", row["commit_ref"], "")

    already = await make("published", commit_ref="deadbeef")
    check("mark-published refuses an already published row",
          await db.mark_article_published_by_hand(already), False)
    check("refused row keeps its commit_ref",
          (await get(already))["commit_ref"], "deadbeef")

    writing = await make("writing")
    check("mark-published refuses a row still being written",
          await db.mark_article_published_by_hand(writing), False)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
