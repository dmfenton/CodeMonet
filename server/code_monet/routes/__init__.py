"""Route modules for the Code Monet API.

This package contains FastAPI routers extracted from main.py for better
organization and maintainability.
"""

from fastapi import APIRouter

from .apple import router as apple_router
from .auth_dev import router as auth_dev_router
from .canvas import router as canvas_router
from .debug import router as debug_router
from .gallery import router as gallery_router
from .health import router as health_router
from .paintings import router as paintings_router
from .public_gallery import router as public_gallery_router
from .seo import router as seo_router
from .strokes import router as strokes_router
from .tracing import router as tracing_router


def create_api_router() -> APIRouter:
    """Create aggregated router with all API routes."""
    api_router = APIRouter()

    # Include all route modules
    api_router.include_router(health_router)
    api_router.include_router(tracing_router)
    api_router.include_router(apple_router)
    api_router.include_router(canvas_router)
    api_router.include_router(gallery_router)
    api_router.include_router(paintings_router)
    api_router.include_router(public_gallery_router)
    api_router.include_router(seo_router)
    api_router.include_router(strokes_router)
    api_router.include_router(auth_dev_router)
    api_router.include_router(debug_router)

    return api_router


__all__ = ["create_api_router"]
