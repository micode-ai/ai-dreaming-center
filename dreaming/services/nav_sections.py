"""The one list of navigable sections.

The sidebar and the help page both need to name every section of the app, in
the same order, with the same label and the same URL. Keeping two lists in two
templates had already gone wrong -- the help page was missing the project-level
AI radar -- so the order, label key and path live here and both consumers read
them from one place.

Icons stay in `_sidebar.html`: an inline SVG is markup, not data, and the help
page does not use them. `scripts/smoke_help_sections.py` asserts the sidebar's
rendered links still match this registry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """One navigable page.

    `key` doubles as the help-text lookup (`help.section.<key>`) and, for
    project pages, as the sidebar's `active` marker. `path` is absolute for
    global sections and a suffix appended to `/p/<slug>` for project ones.
    """

    key: str
    title_key: str
    path: str


GLOBAL_SECTIONS: tuple[Section, ...] = (
    Section("projects", "projects.title", "/projects"),
    Section("ai_usage", "p.ai_usage", "/ai-usage"),
    Section("ai_radar", "radar.title", "/ai-radar"),
    Section("articles", "article.queue.title", "/articles"),
    Section("settings", "settings.title", "/settings"),
)

PROJECT_SECTIONS: tuple[Section, ...] = (
    Section("dashboard", "p.dashboard", "/"),
    Section("orchestration", "p.orchestration", "/orchestration"),
    Section("questions", "p.questions", "/questions"),
    Section("live", "p.live", "/live"),
    Section("rotation", "p.rotation", "/rotation"),
    Section("topics", "p.topics", "/topics"),
    Section("kanban", "p.kanban", "/kanban"),
    Section("notes", "p.notes", "/notes"),
    Section("findings", "p.findings", "/findings"),
    Section("tech_debt", "p.tech_debt", "/tech-debt"),
    Section("ideas", "p.ideas", "/ideas"),
    Section("wiki", "p.wiki", "/wiki"),
    Section("wiki_health", "p.wiki_health", "/wiki-health"),
    Section("ai_usage", "p.ai_usage", "/ai-usage"),
    Section("ai_radar", "radar.title", "/ai-radar"),
    Section("articles", "article.title", "/articles"),
    Section("creatives", "creative.title", "/creatives"),
    Section("evolutions", "p.evolutions", "/evolutions"),
    Section("loops", "p.loops", "/loops"),
    Section("loops_templates", "p.loops_templates", "/loops/templates"),
    Section("plans", "p.plans", "/plans"),
    Section("cascade_costs", "p.cascade_costs", "/cascade-costs"),
    Section("contracts", "p.contracts", "/contracts"),
    Section("sidecar_findings", "p.sidecar_findings", "/sidecar-findings"),
    Section("review", "p.review", "/review"),
    Section("settings", "p.settings", "/settings"),
)


# Key under which a project stores the sections it does not want in its nav.
# Hidden, not shown: recording what is switched off means a section added to
# the registry later appears everywhere by default, instead of being invisible
# in every project that predates it.
NAV_HIDDEN_KEY = "nav_hidden_sections"

# Two sections cannot be hidden. The dashboard is where `/p/<slug>/` lands, so
# removing it leaves the project with no entry point; settings is where the
# hiding is configured, so removing it locks the choice in.
ALWAYS_VISIBLE: frozenset[str] = frozenset({"dashboard", "settings"})


def visible_project_sections(hidden) -> tuple[Section, ...]:
    """Project sections minus the ones this project switched off.

    Tolerant of junk in the stored value -- an unknown key is ignored rather
    than raising, so a section removed from the registry does not break the nav
    of every project that had hidden it.
    """
    off = {k for k in (hidden or ()) if k not in ALWAYS_VISIBLE}
    return tuple(s for s in PROJECT_SECTIONS if s.key not in off)


def hideable_sections() -> tuple[Section, ...]:
    """The sections a project is allowed to switch off, in nav order."""
    return tuple(s for s in PROJECT_SECTIONS if s.key not in ALWAYS_VISIBLE)
