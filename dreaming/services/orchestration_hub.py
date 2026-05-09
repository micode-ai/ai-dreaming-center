"""Stub for Wave 3."""


class OrchestrationHub:
    def __init__(self, db, projects):
        self.db = db
        self.projects = projects

    async def publish(self, project_id: int, run_id: str, event_type: str, payload: dict) -> None:
        raise NotImplementedError("OrchestrationHub.publish implemented in Wave 3")
