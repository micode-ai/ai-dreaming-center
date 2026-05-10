"""TTS messages backfill — Wave 3.9 stub.

The orchestrator_tts_messages table is populated by ClaudeSessionTail when it
detects TTS-like tool calls. This module provides a backfill helper for
historical session files. Full implementation deferred — current placeholder
does nothing but is importable.
"""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)


async def backfill_tts(run_id: str, db, hub, claude_projects_dir: str | None = None) -> int:
    """Replay TTS-like messages from a run's JSONL file. Wave 3.9 stub returns 0.

    A real implementation would tail the JSONL, regex-match Bash tool calls
    that look like TTS invocations, and insert orchestrator_tts_messages rows.
    """
    log.info("tts_backfill stub called for run %s", run_id)
    return 0
