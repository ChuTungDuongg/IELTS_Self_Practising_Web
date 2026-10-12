from fastapi import APIRouter

from app.api.v1 import (
    admin,
    analytics,
    assets,
    attempts,
    auth,
    classroom_assignments,
    classrooms,
    content_governance,
    health,
    history,
    listening,
    notifications,
    preferences,
    reading,
    speaking,
    speaking_ai,
    test_sessions,
    tests,
    transfer,
    writing,
    writing_ai,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(preferences.router)
api_router.include_router(admin.router)
api_router.include_router(tests.router)
api_router.include_router(attempts.router)
api_router.include_router(history.router)
api_router.include_router(test_sessions.router)
api_router.include_router(analytics.router)
api_router.include_router(assets.router)
api_router.include_router(reading.router)
api_router.include_router(speaking.router)
api_router.include_router(speaking.runtime_router)
api_router.include_router(speaking_ai.router)
api_router.include_router(listening.router)
api_router.include_router(writing.router)
api_router.include_router(writing_ai.router)
api_router.include_router(transfer.router)
api_router.include_router(content_governance.router)
api_router.include_router(classrooms.router)
api_router.include_router(notifications.router)
api_router.include_router(classroom_assignments.router)
