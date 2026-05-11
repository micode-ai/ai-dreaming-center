"""One-click directory auto-configuration for per-project settings.

Each entry maps a setting key to a path *relative to* the project's working_dir.
`apply()` creates the directory and saves the setting so the dashboard page that
needed it starts working immediately. The user can later edit the path in
Settings if they want a different location.
"""
from __future__ import annotations
from pathlib import Path


DEFAULTS: dict[str, str] = {
    "tech_debt_dir":         "docs/tech-debt",
    "product_ideas_dir":     "docs/product-ideas",
    "wiki_dir":              "docs/wiki",
    "evolutions_dir":        ".claude/agents/_context",
    "loops_dir":             "docs/loops",
    "plans_dir":             "docs/plans",
    "contracts_dir":         "docs/contracts",
    "sidecar_findings_dir":  ".claude/agents/sidecar-findings",
    "learning_notes_dir":    ".claude/agents/learning-notes",
    "findings_dir":          "docs/findings",
}


def default_abs(project, key: str) -> str | None:
    rel = DEFAULTS.get(key)
    if not rel:
        return None
    return str(Path(project.working_dir) / rel)


async def apply(projects_svc, project, key: str) -> str:
    """Create the default directory and persist the setting. Returns abs path."""
    abs_path = default_abs(project, key)
    if abs_path is None:
        raise ValueError(f"no autoconfig default for key '{key}'")
    Path(abs_path).mkdir(parents=True, exist_ok=True)
    await projects_svc.set_setting(project.id, key, abs_path)
    return abs_path


async def apply_all_defaults(projects_svc, project, *, skip_existing: bool = True) -> dict:
    """Apply every default in DEFAULTS that doesn't already have an override.

    Returns {applied: [{key, path}], skipped: [keys]}.
    """
    overrides = await projects_svc.all_settings(project.id)
    applied: list[dict] = []
    skipped: list[str] = []
    for key in DEFAULTS:
        if skip_existing and key in overrides and overrides[key]:
            skipped.append(key)
            continue
        path = await apply(projects_svc, project, key)
        applied.append({"key": key, "path": path})
    return {"applied": applied, "skipped": skipped}
