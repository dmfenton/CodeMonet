"""Apple App Site Association endpoints for iOS Universal Links."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from code_monet.config import settings

router = APIRouter()


@router.get("/.well-known/apple-app-site-association")
async def apple_app_site_association() -> JSONResponse:
    """Apple App Site Association file for Universal Links.

    This tells iOS which URLs should open the app instead of Safari.
    Requires APPLE_TEAM_ID env var to be set.
    """
    if not settings.apple_team_id:
        return JSONResponse(
            content={"error": "APPLE_TEAM_ID not configured"},
            status_code=500,
        )

    app_id = f"{settings.apple_team_id}.{settings.ios_bundle_id}"

    aasa = {
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": app_id,
                    "paths": ["/auth/callback*"],
                }
            ],
        },
        "webcredentials": {
            "apps": [app_id],
        },
    }

    return JSONResponse(
        content=aasa,
        media_type="application/json",
    )
