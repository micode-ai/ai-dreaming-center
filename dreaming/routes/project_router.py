"""Aggregator router for /p/{slug}/* routes — Wave 1 portion."""
from __future__ import annotations
from fastapi import APIRouter

from dreaming.routes.project_dashboard import router as dashboard_router
from dreaming.routes.project_live import router as live_router
from dreaming.routes.project_rotation import router as rotation_router
from dreaming.routes.project_settings import router as project_settings_router
from dreaming.routes.project_topics import router as topics_router
from dreaming.routes.project_kanban import router as kanban_router
from dreaming.routes.project_notes import router as notes_router


router = APIRouter()
router.include_router(dashboard_router)
router.include_router(live_router)
router.include_router(rotation_router)
router.include_router(topics_router)
router.include_router(kanban_router)
router.include_router(notes_router)
router.include_router(project_settings_router)
