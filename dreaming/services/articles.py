"""Article pipeline helpers: who writes, and may this draft be published.

The center never owns the article's format — see the spec at
docs/superpowers/specs/2026-08-20-article-pipeline-design.md. These are the two
decisions it does own: which agent to hand the brief to, and whether the
publish button is allowed to claim the draft was verified.
"""
from __future__ import annotations
import hashlib
import re
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


_LEGAL_PUBLISH_MODES = ("off", "commit", "commit+push")


def normalize_publish_mode(publish_mode: str) -> str:
    """Case/whitespace-insensitive; anything outside the three legal values
    reads as 'off' (M4) rather than silently behaving like the nearest legal
    one — `"Off"` must not enable publishing, and `"commit+push "` (a
    trailing-space typo) must not quietly degrade into commit-only."""
    mode = (publish_mode or "").strip().lower()
    return mode if mode in _LEGAL_PUBLISH_MODES else "off"


def can_publish(
    row: dict, verify_cmd: str, publish_mode: str,
) -> tuple[bool, str]:
    """(allowed, reason_key). reason_key is an i18n key suffix under article.gate.

    A red verification never becomes a green publish. A missing verification
    command does not block publishing — that would make the feature useless in
    accounting-ai-agent, whose markdown blog has no build step — but the label
    then says 'unverified' everywhere it is shown.
    """
    if normalize_publish_mode(publish_mode) == "off":
        return False, "mode_off"
    if row.get("status") != "drafted":
        return False, "not_drafted"
    if verify_cmd.strip() and not row.get("verify_ok"):
        return False, "verify_failed"
    return True, "ok"


_SLUG_DROP = re.compile(r"[^a-z0-9]+")
_SLUG_WORDS = 6


def slugify(text: str, *, max_words: int = _SLUG_WORDS) -> str:
    """Short hyphenated ASCII slug, mirroring blog-writer.md's slug rule.

    Cyrillic characters drop out rather than being transliterated: the writer
    agent picks the real keyword slug, and this is only a seed for the proposal
    row. An all-Cyrillic title therefore yields a short or empty slug, and the
    caller must fall back to the id.

    `slug_hint` is only a seed for the writer, not the published slug, so
    uniqueness matters more than prettiness here. Truncating to `max_words`
    would otherwise let two distinct titles that share their first
    `max_words` words collide on the same slug — and since
    (project_id, slug_hint) is unique, the second proposal would come back
    as a silently swallowed "duplicate" it never was. So when truncation
    actually drops words, a short hash of the full (untruncated) title is
    appended to keep distinct titles apart; a title that fits within
    `max_words` is left exactly as clean as before, with no suffix.
    """
    low = (text or "").strip().lower()
    words = [w for w in _SLUG_DROP.sub(" ", low).split() if w]
    if len(words) > max_words:
        digest = hashlib.sha1(low.encode("utf-8")).hexdigest()[:6]
        return "-".join(words[:max_words] + [digest])
    return "-".join(words)
