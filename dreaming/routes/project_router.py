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
from dreaming.routes.project_findings import router as findings_router
from dreaming.routes.project_tech_debt import router as tech_debt_router
from dreaming.routes.project_ideas import router as ideas_router
from dreaming.routes.project_wiki import router as wiki_router
from dreaming.routes.project_ai_usage import router as ai_usage_router
from dreaming.routes.project_evolutions import router as evolutions_router
from dreaming.routes.project_loops import router as loops_router
from dreaming.routes.project_plans import router as plans_router
from dreaming.routes.project_cascade_costs import router as cascade_costs_router
from dreaming.routes.project_orchestration import router as orchestration_router
from dreaming.routes.project_questions import router as questions_router
from dreaming.routes.project_session_log import router as session_log_router
from dreaming.routes.project_contracts import router as contracts_router
from dreaming.routes.project_sidecar_findings import router as sidecar_router


router = APIRouter()
router.include_router(dashboard_router)
router.include_router(live_router)
router.include_router(rotation_router)
router.include_router(topics_router)
router.include_router(kanban_router)
router.include_router(notes_router)
router.include_router(findings_router)
router.include_router(tech_debt_router)
router.include_router(ideas_router)
router.include_router(wiki_router)
router.include_router(ai_usage_router)
router.include_router(evolutions_router)
router.include_router(loops_router)
router.include_router(plans_router)
router.include_router(cascade_costs_router)
router.include_router(orchestration_router)
router.include_router(questions_router)
router.include_router(session_log_router)
router.include_router(contracts_router)
router.include_router(sidecar_router)
router.include_router(project_settings_router)
