from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    assets,
    attempts,
    health,
    history,
    listening,
    reading,
    test_sessions,
    tests,
    transfer,
    writing,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tests.router)
api_router.include_router(attempts.router)
api_router.include_router(history.router)
api_router.include_router(test_sessions.router)
api_router.include_router(analytics.router)
api_router.include_router(assets.router)
api_router.include_router(reading.router)
api_router.include_router(listening.router)
api_router.include_router(writing.router)
api_router.include_router(transfer.router)
