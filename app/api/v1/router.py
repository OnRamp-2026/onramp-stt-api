from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.internal_transcriptions import router as internal_transcriptions_router

v1_router = APIRouter()
v1_router.include_router(health_router)
v1_router.include_router(internal_transcriptions_router)
