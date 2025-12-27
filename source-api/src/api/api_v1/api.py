from api.api_v1.endpoints import health, uploads
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(uploads.router, tags=["uploads"])
