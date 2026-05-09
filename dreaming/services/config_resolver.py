"""Config resolver — per-project override → global default."""
from __future__ import annotations
from typing import Any, Optional
from dreaming.services.projects import ProjectsService, Project


_SENTINEL = object()


class ConfigResolver:
    """Per-request resolver. Cache project_settings dict per project to avoid N+1."""

    def __init__(self, projects: ProjectsService, global_settings):
        self.projects = projects
        self.global_settings = global_settings
        self._cache: dict[int, dict] = {}

    async def _project_settings(self, project: Project) -> dict:
        if project.id not in self._cache:
            self._cache[project.id] = await self.projects.all_settings(project.id)
        return self._cache[project.id]

    async def get(
        self, project: Optional[Project], key: str, default: Any = _SENTINEL,
    ) -> Any:
        if project is not None:
            ps = await self._project_settings(project)
            if key in ps:
                return ps[key]
        gv = getattr(self.global_settings, key, _SENTINEL)
        if gv is not _SENTINEL:
            return gv
        if default is _SENTINEL:
            return None
        return default

    def invalidate_project(self, project_id: int) -> None:
        self._cache.pop(project_id, None)
