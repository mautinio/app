from fastapi import APIRouter

from app.api.routes import campaigns, catalog, streams

router = APIRouter(prefix="/api")
router.include_router(catalog.router)
router.include_router(campaigns.router)
router.include_router(streams.router)
