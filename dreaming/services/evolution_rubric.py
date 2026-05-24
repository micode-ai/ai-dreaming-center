"""5-мерная rubric для оценки evolution-предложений.

Адаптация src/learning/rubric.ts из anthroclaw. Идея: формализовать критерии
качества «улучшений», предлагаемых /evolve-agent, чтобы weekly_evolve_apply
не применял шумовые предложения.

Rubric встраивается в YAML-frontmatter evolution-отчёта (опционально):

    ---
    rubric:
      evidence_strength: strong       # weak | medium | strong
      durability: durable             # one_off | session | durable
      reusability: cross_agent        # none | agent_specific | cross_agent
      safety: safe                    # safe | needs_review | unsafe
      recommended_action: skill       # memory | skill | none
      notes: "Подтверждено 4 incidents in арсений+миша"
    ---

Правило: автоприменение возможно только если evidence_strength != weak AND
durability != one_off AND safety != unsafe. Иначе → отметить в UI как
"requires manual review" / "rejected".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


class Evidence(str, Enum):
    weak = "weak"
    medium = "medium"
    strong = "strong"


class Durability(str, Enum):
    one_off = "one_off"
    session = "session"
    durable = "durable"


class Reusability(str, Enum):
    none = "none"
    agent_specific = "agent_specific"
    cross_agent = "cross_agent"


class Safety(str, Enum):
    safe = "safe"
    needs_review = "needs_review"
    unsafe = "unsafe"


class Action(str, Enum):
    memory = "memory"
    skill = "skill"
    none = "none"


@dataclass
class EvolutionRubric:
    """5-мерная оценка предложения."""

    evidence_strength: Evidence | None = None
    durability: Durability | None = None
    reusability: Reusability | None = None
    safety: Safety | None = None
    recommended_action: Action | None = None
    notes: str = ""

    raw: dict[str, Any] = field(default_factory=dict)
    invalid_fields: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return all(
            getattr(self, f) is not None
            for f in ("evidence_strength", "durability", "safety", "recommended_action")
        )

    @property
    def auto_apply_eligible(self) -> bool:
        """Можно ли применять без ручного review."""
        if not self.is_complete:
            return False
        if self.evidence_strength == Evidence.weak:
            return False
        if self.durability == Durability.one_off:
            return False
        if self.safety in (Safety.needs_review, Safety.unsafe):
            return False
        if self.recommended_action == Action.none:
            return False
        return True

    @property
    def verdict(self) -> str:
        """Короткий текст: 'auto' | 'review' | 'reject' | 'incomplete'."""
        if not self.is_complete:
            return "incomplete"
        if self.safety == Safety.unsafe:
            return "reject"
        if self.auto_apply_eligible:
            return "auto"
        return "review"

    @property
    def verdict_reason(self) -> str:
        reasons: list[str] = []
        if not self.is_complete:
            reasons.append("rubric неполная")
            return ", ".join(reasons)
        if self.evidence_strength == Evidence.weak:
            reasons.append("evidence=weak")
        if self.durability == Durability.one_off:
            reasons.append("durability=one_off")
        if self.safety == Safety.unsafe:
            reasons.append("safety=unsafe")
        elif self.safety == Safety.needs_review:
            reasons.append("safety=needs_review")
        if self.recommended_action == Action.none:
            reasons.append("action=none")
        return ", ".join(reasons) if reasons else "все критерии пройдены"


# ── Frontmatter parsing ───────────────────────────────────────────────


_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def extract_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Возвращает (frontmatter_dict, body). Если frontmatter нет — ({}, text)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
        if not isinstance(data, dict):
            return {}, text
    except yaml.YAMLError as e:
        log.warning("Frontmatter parse error: %s", e)
        return {}, text
    body = text[m.end():]
    return data, body


def _coerce_enum(val: Any, enum_cls, field_name: str, invalid: list[str]):
    if val is None:
        return None
    try:
        return enum_cls(str(val))
    except (ValueError, KeyError):
        invalid.append(f"{field_name}={val!r}")
        return None


def parse_rubric(frontmatter: dict[str, Any]) -> EvolutionRubric | None:
    """Извлечь rubric из YAML-frontmatter. None если секции `rubric:` нет."""
    if not isinstance(frontmatter, dict):
        return None
    raw = frontmatter.get("rubric")
    if not isinstance(raw, dict):
        return None
    invalid: list[str] = []
    rubric = EvolutionRubric(
        evidence_strength=_coerce_enum(
            raw.get("evidence_strength"), Evidence, "evidence_strength", invalid
        ),
        durability=_coerce_enum(raw.get("durability"), Durability, "durability", invalid),
        reusability=_coerce_enum(
            raw.get("reusability"), Reusability, "reusability", invalid
        ),
        safety=_coerce_enum(raw.get("safety"), Safety, "safety", invalid),
        recommended_action=_coerce_enum(
            raw.get("recommended_action"), Action, "recommended_action", invalid
        ),
        notes=str(raw.get("notes") or "").strip(),
        raw=raw,
        invalid_fields=invalid,
    )
    return rubric


def parse_rubric_from_file(path: Path | str) -> EvolutionRubric | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    fm, _ = extract_frontmatter(text)
    return parse_rubric(fm)


# ── Aggregated report ─────────────────────────────────────────────────


@dataclass
class ReportRubricStats:
    total: int = 0
    with_rubric: int = 0
    auto: int = 0
    review: int = 0
    reject: int = 0
    incomplete: int = 0


def collect_stats(evolutions_dir: str | Path) -> ReportRubricStats:
    """Прогон по всем reports и подсчёт распределения verdict-ов."""
    p = Path(evolutions_dir)
    stats = ReportRubricStats()
    if not p.exists():
        return stats
    for f in p.glob("*.md"):
        if f.stem.startswith("_"):
            continue
        stats.total += 1
        r = parse_rubric_from_file(f)
        if r is None:
            continue
        stats.with_rubric += 1
        v = r.verdict
        if v == "auto":
            stats.auto += 1
        elif v == "review":
            stats.review += 1
        elif v == "reject":
            stats.reject += 1
        else:
            stats.incomplete += 1
    return stats
