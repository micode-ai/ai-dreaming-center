"""Smoke test: topics ingest endpoint + prompt-injection helper.

Runs against a live dev server on port 8086. Picks any enabled project,
inserts 3 topics via POST /api/p/{slug}/topics/ingest, queries them via
GET /topics/list, calls build_topics_extra_prompt directly against the
same DB, asserts the generated block contains all 3 titles, and cleans up.

Exit code 0 on success, non-zero on any failure.
"""
from __future__ import annotations
import asyncio
import json
import sys
import sqlite3
import urllib.error
import urllib.request

BASE = "http://localhost:8086"
DB_PATH = "data/dreaming.db"


def http_json(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def pick_enabled_slug():
    """Find any enabled project slug directly from the DB."""
    c = sqlite3.connect(DB_PATH)
    try:
        row = c.execute(
            "SELECT slug FROM projects WHERE enabled=1 LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        c.close()


async def main():
    slug = pick_enabled_slug()
    if slug is None:
        print("FAIL: no enabled projects in DB", file=sys.stderr)
        return 1
    print(f"using project: {slug}")

    titles = ["SMOKE topic alpha", "SMOKE topic beta", "SMOKE topic gamma"]
    ids = []
    for title in titles:
        status, body = http_json("POST", f"/api/p/{slug}/topics/ingest", {
            "title": title, "module": "smoke",
            "target_agents": "smoke-agent",
            "question": "?", "why_important": "smoke",
        })
        if status != 201:
            print(f"FAIL ingest: {status} {body}", file=sys.stderr)
            return 1
        ids.append(body["id"])
    print(f"ingested {len(ids)} topics")

    status, listing = http_json("GET", f"/api/p/{slug}/topics/list")
    listed_titles = {t["title"] for t in listing} if isinstance(listing, list) else set()
    missing = set(titles) - listed_titles
    if missing:
        print(f"FAIL list: missing {missing}", file=sys.stderr)
        return 1
    print(f"list shows all {len(titles)} titles")

    from dreaming.services.db import SqliteDB
    from dreaming.services.topics_prompt import build_topics_extra_prompt

    db = SqliteDB(DB_PATH)
    await db.connect()
    try:
        row = await db.fetch_one(
            "SELECT id FROM projects WHERE slug=?", (slug,),
        )
        if row is None:
            print(f"FAIL: project '{slug}' vanished mid-test", file=sys.stderr)
            return 1
        pid = row["id"]
        block = await build_topics_extra_prompt(db, pid, "smoke-agent")
        missing_in_block = [t for t in titles if t not in block]
        if missing_in_block:
            print(f"FAIL helper: missing titles in block: {missing_in_block}",
                  file=sys.stderr)
            print(f"--- block ---\n{block}\n---", file=sys.stderr)
            return 1
        print("helper block contains all titles")

        for tid in ids:
            await db.delete_custom_topic(pid, tid)
        print(f"cleaned up {len(ids)} topics. OK.")
    finally:
        await db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
