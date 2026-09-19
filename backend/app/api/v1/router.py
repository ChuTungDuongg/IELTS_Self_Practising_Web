from fastapi import APIRouter

from app.api.v1 import assets, attempts, health, history, listening, reading, tests

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tests.router)
api_router.include_router(attempts.router)
api_router.include_router(history.router)
api_router.include_router(assets.router)
api_router.include_router(reading.router)
api_router.include_router(listening.router)
