"""Per-project bulk orchestration queue.

Lets the UI submit many findings/ideas/evolutions at once and dispatches them
to the Orchestrator one at a time — the Orchestrator only allows one run per
project simultaneously (see `has_running_run` gate in `start_orchestration_run`),
so naive parallel submission would just bounce all but the first.

Design:
- In-memory queue per project (lost on server restart; that's acceptable —
  Orchestrator runs survive in DB, the queue is just intent-to-dispatch).
- Background asyncio task per project polls `hub.has_running_run` and, when
  the slot is free, dispatches the next pending item.
- Three dispatch helpers (`dispatch_finding`, `dispatch_idea`, `dispatch_evolution`)
  duplicate the goal-building from the route handlers. Refactor target: the
  existing single-item routes should call these too, eventually.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dreaming.services.frontmatter_io import set_frontmatter_field
from dreaming.services.orchestration_dispatch import start_orchestration_run

log = logging.getLogger(__name__)

Kind = Literal["finding", "idea", "evolution"]
_KINDS: set[str] = {"finding", "idea", "evolution"}


@dataclass
class BulkItem:
    kind: Kind
    identifier: str  # findings/ideas: id; evolutions: relative path
    force: bool = False  # evolutions only — bypass conflict gate
    status: str = "pending"  # pending | dispatched | failed | skipped
    run_id: str | None = None
    error: str | None = None


@dataclass
class BulkQueue:
    items: list[BulkItem] = field(default_factory=list)
    dispatching: bool = False  # background task is alive
    last_event_at: float = 0.0  # for staleness display
    # Last slot-check result, surfaced in the UI so the user can see WHY pending
    # items aren't moving. "free" = ready to dispatch; "blocked:<run_id>" = a
    # live Orchestrator run is occupying the project's single slot; "error:<msg>"
    # = the slot check itself threw (dispatcher is treating slot as free and
    # continuing; this status reflects that we noticed).
    last_slot_status: str = ""

    def add(self, kind: Kind, identifier: str, force: bool = False) -> None:
        # De-dup: skip if same kind+identifier is already pending or dispatched.
        for it in self.items:
            if it.kind == kind and it.identifier == identifier and it.status in ("pending", "dispatched"):
                return
        self.items.append(BulkItem(kind=kind, identifier=identifier, force=force))

    def next_pending(self) -> BulkItem | None:
        return next((it for it in self.items if it.status == "pending"), None)

    def pending_count(self) -> int:
        return sum(1 for it in self.items if it.status == "pending")

    def snapshot(self) -> list[dict]:
        return [
            {"kind": it.kind, "identifier": it.identifier, "status": it.status,
             "run_id": it.run_id, "error": it.error}
            for it in self.items
        ]

    def diag(self) -> dict:
        return {
            "dispatching": self.dispatching,
            "last_slot_status": self.last_slot_status,
            "pending": self.pending_count(),
            "failed": sum(1 for it in self.items if it.status == "failed"),
            "dispatched": sum(1 for it in self.items if it.status == "dispatched"),
        }


def get_queue(app_state, project_id: int) -> BulkQueue:
    queues = getattr(app_state, "bulk_queues", None)
    if queues is None:
        queues = {}
        app_state.bulk_queues = queues
    q = queues.get(project_id)
    if q is None:
        q = BulkQueue()
        queues[project_id] = q
    return q


def ensure_dispatcher(app_state, project) -> None:
    """Start the per-project dispatcher task if not already running."""
    queue = get_queue(app_state, project.id)
    if queue.dispatching:
        return
    queue.dispatching = True
    asyncio.create_task(
        _dispatcher_loop(app_state, project, queue),
        name=f"bulk-dispatch-{project.slug}",
    )


async def _is_slot_blocked(app_state, project) -> bool:
    """A project's orchestration slot is only really blocked if there's a
    `running` row in DB AND a matching live claude process in PM. A row
    without a process is a zombie — typically left over from killing the
    process via the UI without clicking "Force-close all stale". Treating
    such zombies as blockers makes the bulk dispatcher hang indefinitely.
    """
    hub = app_state.orchestration_hub
    pm = app_state.process_manager
    running_id = await hub.has_running_run(project.id)
    if not running_id:
        return False
    # Recognise both new (`orchestrator-`) and legacy ALC (`roman-`) cmd keys.
    live_session_ids = {
        getattr(sess, "session_id", "") or ""
        for key, sess in pm.list_running().items()
        if key.startswith(f"cmd:{project.slug}:orchestrator-")
        or key.startswith(f"cmd:{project.slug}:roman-")
    }
    run_row = await hub.get_run(running_id)
    if run_row is None:
        return False
    try:
        ext = run_row["external_id"] or ""
    except (IndexError, KeyError):
        ext = ""
    if ext and ext in live_session_ids:
        return True
    # DB says running but no live process — auto-cancel so the orchestration
    # list stops showing "stale" too. Best-effort; ignore failures.
    try:
        await hub.finish_run(
            running_id, status="cancelled",
            error_message="auto-cancelled by bulk dispatcher (no live process)",
        )
        log.info("bulk dispatcher [%s]: auto-cancelled stale run %s",
                 project.slug, running_id)
    except Exception as e:
        log.warning("bulk dispatcher [%s]: auto-cancel of stale run %s failed: %s",
                    project.slug, running_id, e)
    return False


async def _safe_slot_blocked(app_state, project, queue: BulkQueue) -> bool:
    """Slot check that NEVER crashes the dispatcher loop. Any exception during
    DB/PM probing is treated as "slot free" (fail-open) so the queue keeps
    flowing — better to dispatch and have start_orchestration_run reject than
    to wedge pending items forever on a transient DB hiccup."""
    try:
        blocked = await _is_slot_blocked(app_state, project)
    except Exception as e:
        queue.last_slot_status = f"error:{type(e).__name__}: {e}"
        log.warning("bulk dispatcher [%s]: slot check raised, treating as free: %s",
                    project.slug, e)
        return False
    if blocked:
        # Re-resolve which run we're waiting on so the UI can name it.
        try:
            running_id = await app_state.orchestration_hub.has_running_run(project.id)
            queue.last_slot_status = f"blocked:{running_id or 'unknown'}"
        except Exception:
            queue.last_slot_status = "blocked:unknown"
    else:
        queue.last_slot_status = "free"
    return blocked


async def _dispatcher_loop(app_state, project, queue: BulkQueue) -> None:
    try:
        while True:
            item = queue.next_pending()
            if item is None:
                queue.last_slot_status = ""
                break
            # Wait for the project's orchestration slot to be free.
            # No hard timeout — Orchestrator runs can legitimately last hours;
            # if user wants to abort, they can manually mark the active run
            # completed or kill via the UI.
            while await _safe_slot_blocked(app_state, project, queue):
                await asyncio.sleep(2)
            try:
                run_id = await _dispatch_one(app_state, project, item)
                item.run_id = run_id
                item.status = "dispatched"
                log.info("bulk dispatcher [%s]: dispatched %s %s -> run %s",
                         project.slug, item.kind, item.identifier, run_id)
            except Exception as e:
                item.status = "failed"
                item.error = f"{type(e).__name__}: {e}"
                log.warning("bulk dispatcher [%s]: failed %s %s: %s",
                            project.slug, item.kind, item.identifier, e)
            # Brief pause so the new run registers in DB before the next
            # slot check; otherwise we'd race the next item past the gate.
            await asyncio.sleep(3)
    except Exception as e:
        # Defensive: catch anything that escapes the per-item try so the loop
        # can't die silently and leave dispatching=False with pending items.
        log.exception("bulk dispatcher [%s]: loop crashed: %s", project.slug, e)
        queue.last_slot_status = f"error:{type(e).__name__}: {e}"
    finally:
        queue.dispatching = False


async def _dispatch_one(app_state, project, item: BulkItem) -> str:
    if item.kind == "finding":
        return await dispatch_finding(app_state, project, item.identifier)
    if item.kind == "idea":
        return await dispatch_idea(app_state, project, item.identifier)
    if item.kind == "evolution":
        return await dispatch_evolution(app_state, project, item.identifier, force=item.force)
    raise ValueError(f"unknown bulk kind: {item.kind}")


# ── dispatch helpers (mirror the per-item route handlers) ──────────────


async def dispatch_finding(app_state, project, item_id: str) -> str:
    from dreaming.services.tech_debt import read_tech_debt_item, read_td
    from dreaming.services.frontmatter_io import find_md_file

    from dreaming.services.config_resolver import ConfigResolver
    resolver = ConfigResolver(app_state.projects, app_state.settings)
    td_dir = await resolver.get(project, "tech_debt_dir", "")
    if not td_dir:
        raise ValueError("tech_debt_dir not set")
    item = read_tech_debt_item(td_dir, item_id)
    if item is None:
        raise FileNotFoundError(f"finding {item_id} not found")
    item_dict = dict(item.__dict__) if hasattr(item, "__dict__") else {}
    title = item_dict.get("title") or item_id
    fp = item_dict.get("file_path")

    # Idempotency: existing run still around → reuse, don't enqueue a duplicate.
    existing_run_id = (item_dict.get("orchestration_run") or "").strip()
    if existing_run_id:
        hub = app_state.orchestration_hub
        existing_row = await hub.get_run(existing_run_id)
        if existing_row is not None and existing_row["project_id"] == project.id:
            return existing_run_id

    body_md = ""
    if fp:
        try:
            _, body_md = read_td(fp)
        except Exception:
            body_md = ""
    goal = (
        f"Реши tech-debt: «{title}» (id `{item_id}`).\n\n"
        f"{body_md[:4000]}\n\n"
        f"Когда закончишь, обнови frontmatter `status:` в "
        f"`{fp or (td_dir + '/' + item_id + '.md')}` на `closed` "
        f"(или `dropped`, если решил, что это не баг)."
    )
    result = await start_orchestration_run(app_state, project, goal)
    path = find_md_file(td_dir, item_id, fallback_paths=[fp] if fp else None)
    if path is not None and result.get("run_id"):
        set_frontmatter_field(path, "orchestration_run", result["run_id"])
    return result["run_id"]


async def dispatch_idea(app_state, project, item_id: str) -> str:
    from dreaming.services.product_ideas import list_product_ideas, read_product_idea
    from dreaming.services.frontmatter_io import find_md_file

    from dreaming.services.config_resolver import ConfigResolver
    resolver = ConfigResolver(app_state.projects, app_state.settings)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    if not ideas_dir:
        raise ValueError("product_ideas_dir not set")
    target = None
    for it in list_product_ideas(ideas_dir):
        obj = it.__dict__ if hasattr(it, "__dict__") else (it if isinstance(it, dict) else {})
        if obj.get("id") == item_id or obj.get("slug") == item_id:
            target = obj
            break
    if target is None:
        raise FileNotFoundError(f"idea {item_id} not found")

    existing_run_id = (target.get("orchestration_run") or "").strip()
    if existing_run_id:
        hub = app_state.orchestration_hub
        existing_row = await hub.get_run(existing_run_id)
        if existing_row is not None and existing_row["project_id"] == project.id:
            return existing_run_id

    path = find_md_file(ideas_dir, item_id)
    body_md = ""
    if path is not None:
        try:
            _, body_md = read_product_idea(str(path))
        except Exception:
            body_md = ""
    title = target.get("title") or item_id
    goal = (
        f"Реализуй product-idea: «{title}» (id `{item_id}`).\n\n"
        f"{body_md[:4000]}\n\n"
        f"Когда закончишь, обнови frontmatter `status:` в файле идеи на "
        f"`building` или `shipped`."
    )
    result = await start_orchestration_run(app_state, project, goal)
    if path is not None and result.get("run_id"):
        set_frontmatter_field(path, "orchestration_run", result["run_id"])
    return result["run_id"]


async def dispatch_evolution(
    app_state, project, relative_path: str, *, force: bool = False,
) -> str:
    from dreaming.services.evolutions import list_evolutions

    from dreaming.services.config_resolver import ConfigResolver
    resolver = ConfigResolver(app_state.projects, app_state.settings)
    default_dir = str(Path(project.working_dir) / ".claude" / "agents" / "_context")
    evolutions_dir = (await resolver.get(project, "evolutions_dir", "")
                      or await resolver.get(project, "context_overrides_dir", "")
                      or default_dir)

    base = Path(evolutions_dir).resolve()
    if not base.exists():
        raise FileNotFoundError(f"evolutions_dir {evolutions_dir} not found")
    target = (base / relative_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(f"path traversal rejected: {relative_path}")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"evolution {relative_path} not found")

    if not force:
        items = list_evolutions(evolutions_dir)
        same = next((it for it in items if it.path == str(target)), None)
        if same and same.has_conflict:
            raise ValueError(
                f"evolution '{same.name}' has unresolved conflict with another "
                f"open proposal targeting agent '{same.agent_name}'; resubmit with force=1"
            )

    text = target.read_text(encoding="utf-8")
    m = re.search(r"(?m)^agent\s*:\s*(.+?)\s*$", text)
    agent_name = m.group(1).strip().strip("'\"") if m else target.parent.name
    agent_file = Path(project.working_dir) / ".claude" / "agents" / f"{agent_name}.md"
    goal = (
        f"Применить evolution-предложение к агент-файлу `{agent_file}`.\n\n"
        f"Содержание evolution-файла `{relative_path}`:\n\n"
        f"{text[:5000]}\n\n"
        f"Шаги:\n"
        f"1. Прочитай текущий `{agent_file}` (если существует).\n"
        f"2. Примени правки из раздела «Proposed change» evolution-файла. "
        f"   Сохрани стиль и структуру существующего агент-файла.\n"
        f"3. Если изменение конфликтует с другими разделами — отметь это "
        f"   в конце агент-файла секцией «## Open questions» вместо переписывания.\n"
        f"4. Обнови frontmatter evolution-файла `{target}` на "
        f"   `status: applied` и добавь `applied_at: <today YYYY-MM-DD>`.\n"
        f"5. Заверши run."
    )
    result = await start_orchestration_run(app_state, project, goal)
    if result.get("run_id"):
        set_frontmatter_field(target, "orchestration_run", result["run_id"])
    return result["run_id"]
