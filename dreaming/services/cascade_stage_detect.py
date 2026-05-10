"""Heuristic detector: agent_name + description → cascade stage key.

Used as a fallback when no explicit mapping is set in
settings.cascade_stage_by_agent. The result is also used to suggest
defaults in the /settings UI for new agent rosters.

Returns one of: 'contract' | 'design' | 'implementation' | 'review' | 'qa'
or None if no rule matched (then orchestration falls back to attaching
the node to the currently active stage).
"""

from __future__ import annotations

import re

# Order matters: first matching rule wins. Each rule is
# (stage_key, name_patterns, description_patterns).
_RULES: list[tuple[str, list[str], list[str]]] = [
    (
        "contract",
        [r"-business$", r"-product$", r"^business-", r"^product-"],
        [r"\bbusiness\b", r"product owner", r"requirements", r"контракт"],
    ),
    (
        "design",
        [r"-orchestrator$", r"-architect$", r"-lead$", r"^architect-"],
        [r"architect", r"orchestrator", r"team lead", r"архитект"],
    ),
    (
        "review",
        [
            r"-reviewer$", r"-security$", r"-bug-hunter$", r"-failure-hunter$",
            r"-api-tester$", r"-stress$",
        ],
        [
            r"\breview\b", r"security", r"auditor", r"\bbug\b",
            r"regression", r"tester", r"performance",
        ],
    ),
    (
        "qa",
        [r"-qa$", r"-docs-writer$", r"-acceptance$"],
        [r"\bqa\b", r"acceptance", r"documentation", r"приёмка", r"docs writer"],
    ),
    (
        "implementation",
        [
            r"-frontend$", r"-backend$", r"-dba$", r"-fullstack$", r"-n8n$",
            r"-workflow$", r"-i18n$", r"-ui-designer$", r"-coder$",
            r"-engineer$", r"-developer$",
        ],
        [
            r"frontend", r"backend", r"\bdba\b", r"developer", r"engineer",
            r"\bcoder\b", r"i18n", r"designer",
        ],
    ),
]


def detect_stage(agent_name: str, description: str = "") -> str | None:
    """Suggest a cascade stage for an agent based on name + description.

    >>> detect_stage("alisa-frontend")
    'implementation'
    >>> detect_stage("vera-reviewer")
    'review'
    >>> detect_stage("forecast-expert")  # not in any rule
    """
    name = (agent_name or "").lower().strip()
    desc = (description or "").lower()
    for stage_key, name_pats, desc_pats in _RULES:
        for pat in name_pats:
            if re.search(pat, name):
                return stage_key
        for pat in desc_pats:
            if re.search(pat, desc):
                return stage_key
    return None
