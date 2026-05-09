"""Smoke test ProcessManager API surface after Wave 1 Phase 1.1 port.

Boots the full FastAPI lifespan, then introspects the wired ProcessManager
to confirm the new (project, *, agent_name=...) signature and helper methods.
Does NOT spawn a real claude process.
"""
from __future__ import annotations

import asyncio
import inspect

from dreaming.main import app


async def main() -> None:
    async with app.router.lifespan_context(app):
        pm = app.state.process_manager
        assert hasattr(pm, "start_session"), "start_session missing"
        assert hasattr(pm, "list_running"), "list_running missing"
        assert hasattr(pm, "stream_subscriber"), "stream_subscriber missing"
        assert hasattr(pm, "kill"), "kill missing"
        assert hasattr(pm, "reconcile_stale_sessions"), "reconcile_stale_sessions missing"
        assert hasattr(pm, "keep_awake"), "keep_awake missing"

        sig = inspect.signature(pm.start_session)
        params = list(sig.parameters.keys())
        assert params[0] == "project", f"first param is {params[0]}, not 'project'"
        # keyword-only: project is POSITIONAL_OR_KEYWORD, then *,
        ka_kinds = [p.kind for p in sig.parameters.values()]
        # 'agent_name' must be keyword-only
        agent_param = sig.parameters.get("agent_name")
        assert agent_param is not None, "agent_name param missing"
        assert agent_param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"agent_name should be keyword-only, got {agent_param.kind}"
        )

        print("ProcessManager API verified:", params[:3])


if __name__ == "__main__":
    asyncio.run(main())
