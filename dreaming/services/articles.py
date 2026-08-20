"""Article pipeline helpers: who writes, and may this draft be published.

The center never owns the article's format — see the spec at
docs/superpowers/specs/2026-08-20-article-pipeline-design.md. These are the two
decisions it does own: which agent to hand the brief to, and whether the
publish button is allowed to claim the draft was verified.
"""
from __future__ import annotations
from pathlib import Path


# Substrings that mark an agent as one that writes prose, most specific first.
# Ordered so `blog-writer` beats a generic `*-author` when a repo has both.
_WRITER_HINTS = (
    "blog-writer", "article", "kb-page-author", "copywriter",
    "content-writer", "tech-writer", "writer", "author",
)
# An agent whose name matches a hint but is not a prose writer.
_WRITER_EXCLUDE = ("test-author", "component-author", "test-runner")


def resolve_writer(working_dir: str | Path, configured: str = "") -> str:
    """Configured agent wins; else autodetect in .claude/agents; else 'self'.

    Only three of eleven projects ship a writing agent, so 'self' is a normal
    outcome, not a failure — the slash-command writes the piece itself and the
    card records `writer_agent='self'` so the UI stays honest about it.
    """
    if configured.strip():
        return configured.strip()
    agents_dir = Path(working_dir) / ".claude" / "agents"
    if not agents_dir.is_dir():
        return "self"
    names = sorted(p.stem for p in agents_dir.glob("*.md"))
    for hint in _WRITER_HINTS:
        for name in names:
            low = name.lower()
            if hint in low and not any(bad in low for bad in _WRITER_EXCLUDE):
                return name
    return "self"


def publish_label(verify_ok: bool, verify_cmd: str) -> str:
    """What the card and the commit message are allowed to claim."""
    if not verify_cmd.strip():
        return "unverified"
    return "verified" if verify_ok else "failed"


def can_publish(
    row: dict, verify_cmd: str, publish_mode: str,
) -> tuple[bool, str]:
    """(allowed, reason_key). reason_key is an i18n key suffix under article.gate.

    A red verification never becomes a green publish. A missing verification
    command does not block publishing — that would make the feature useless in
    accounting-ai-agent, whose markdown blog has no build step — but the label
    then says 'unverified' everywhere it is shown.
    """
    if (publish_mode or "off").strip() == "off":
        return False, "mode_off"
    if row.get("status") != "drafted":
        return False, "not_drafted"
    if verify_cmd.strip() and not row.get("verify_ok"):
        return False, "verify_failed"
    return True, "ok"
