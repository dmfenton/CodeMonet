"""Share routes for public canvas sharing with social media support."""

import html
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from code_monet.auth.dependencies import CurrentUser
from code_monet.canvas import render_path_to_svg_d
from code_monet.config import settings
from code_monet.db import CanvasShare, get_session, repository
from code_monet.rendering import options_for_share_preview, render_strokes_async
from code_monet.types import DrawingStyleType, Path, get_style_config
from code_monet.workspace import WorkspaceState

router = APIRouter(prefix="/s", tags=["share"])


def generate_share_token() -> str:
    """Generate a URL-safe share token (10 chars, ~60 bits of entropy)."""
    return secrets.token_urlsafe(8)[:10]


class CreateShareRequest(BaseModel):
    """Request to create a share link."""

    piece_number: int
    title: str | None = None


class ShareResponse(BaseModel):
    """Response with share link info."""

    token: str
    url: str
    piece_number: int
    title: str | None
    created_at: str


# =============================================================================
# Authenticated endpoints for creating/managing shares
# =============================================================================


@router.post("/create", response_model=ShareResponse)
async def create_share(request: CreateShareRequest, user: CurrentUser) -> ShareResponse:
    """Create a public share link for a gallery piece."""
    # Verify the piece exists
    state = await WorkspaceState.load_for_user(user.id)
    strokes = await state.load_from_gallery(request.piece_number)
    if strokes is None:
        raise HTTPException(status_code=404, detail="Piece not found in gallery")

    async with get_session() as session:
        # Check if share already exists for this piece
        existing = await repository.get_canvas_share_by_user_piece(
            session, user.id, request.piece_number
        )
        if existing:
            return ShareResponse(
                token=existing.token,
                url=f"{settings.magic_link_base_url}/s/{existing.token}",
                piece_number=existing.piece_number,
                title=existing.title,
                created_at=existing.created_at.isoformat(),
            )

        # Create new share
        token = generate_share_token()
        share = await repository.create_canvas_share(
            session,
            token=token,
            user_id=user.id,
            piece_number=request.piece_number,
            title=request.title,
        )

        return ShareResponse(
            token=share.token,
            url=f"{settings.magic_link_base_url}/s/{share.token}",
            piece_number=share.piece_number,
            title=share.title,
            created_at=share.created_at.isoformat(),
        )


@router.get("/my-shares", response_model=list[ShareResponse])
async def list_my_shares(user: CurrentUser) -> list[ShareResponse]:
    """List all share links for the current user."""
    async with get_session() as session:
        shares = await repository.list_user_shares(session, user.id)
        return [
            ShareResponse(
                token=s.token,
                url=f"{settings.magic_link_base_url}/s/{s.token}",
                piece_number=s.piece_number,
                title=s.title,
                created_at=s.created_at.isoformat(),
            )
            for s in shares
        ]


@router.delete("/{token}")
async def delete_share(token: str, user: CurrentUser) -> dict[str, str]:
    """Delete a share link."""
    async with get_session() as session:
        deleted = await repository.delete_canvas_share(session, token, user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Share not found or not owned by you")
        return {"status": "deleted"}


# =============================================================================
# Public endpoints (no auth required) - SSR for social media
# =============================================================================


async def load_shared_canvas(
    token: str,
) -> tuple[CanvasShare, list[Path], DrawingStyleType, int, int]:
    """Load share info, canvas strokes, drawing style, and dimensions."""
    async with get_session() as session:
        share = await repository.get_canvas_share(session, token)
        if share is None:
            raise HTTPException(status_code=404, detail="Share not found")

        # Load the piece from user's gallery
        state = await WorkspaceState.load_for_user(share.user_id)
        result = await state.load_from_gallery(share.piece_number)
        if result is None:
            raise HTTPException(status_code=404, detail="Artwork no longer exists")

        strokes, drawing_style, width, height = result
        return share, strokes, drawing_style, width, height


@router.get("/{token}/preview.png")
async def get_share_preview_image(token: str) -> Response:
    """Get preview image for social media sharing (no auth required)."""
    _share, strokes, drawing_style, width, height = await load_shared_canvas(token)

    options = options_for_share_preview(drawing_style, width, height)
    result = await render_strokes_async(strokes, options)
    assert isinstance(result, bytes)

    return Response(
        content=result,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        },
    )


@router.get("/{token}", response_class=HTMLResponse)
async def get_share_page(token: str) -> HTMLResponse:
    """Serve SSR HTML page with Open Graph meta tags for social sharing."""
    share, strokes, drawing_style, width, height = await load_shared_canvas(token)
    style_config = get_style_config(drawing_style)

    # Build meta info - escape user-provided content to prevent XSS
    raw_title = share.title or f"Artwork #{share.piece_number}"
    title = html.escape(raw_title)
    description = "Created with Monet - AI-powered collaborative art"
    share_url = f"{settings.magic_link_base_url}/s/{token}"
    preview_url = f"{share_url}/preview.png"
    app_store_url = "https://apps.apple.com/app/monet-ai-art/id6740019844"

    # Render SVG inline for the page - escape path data to prevent injection
    svg_paths = ""
    for path in strokes:
        d = render_path_to_svg_d(path)
        if d:
            effective_style = path.get_effective_style(style_config)
            escaped_d = html.escape(d, quote=True)
            color = html.escape(effective_style.color, quote=True)
            fill = html.escape(path.fill, quote=True) if path.fill else "none"
            fill_opacity = (
                path.fill_opacity if path.fill_opacity is not None else effective_style.opacity
            )
            stroke_width: float = effective_style.stroke_width
            stroke = color if stroke_width > 0 else "none"
            svg_paths += f'<path d="{escaped_d}" stroke="{stroke}" stroke-width="{stroke_width}" fill="{fill}" fill-opacity="{fill_opacity}" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="{effective_style.opacity}"/>'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | Monet</title>

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="{share_url}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:image" content="{preview_url}">
    <meta property="og:image:width" content="{width}">
    <meta property="og:image:height" content="{height}">
    <meta property="og:site_name" content="Monet">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{share_url}">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{description}">
    <meta name="twitter:image" content="{preview_url}">

    <!-- Apple Smart App Banner -->
    <meta name="apple-itunes-app" content="app-id=6740019844">

    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }}

        .container {{
            max-width: 600px;
            width: 100%;
        }}

        .logo {{
            text-align: center;
            margin-bottom: 24px;
        }}

        .logo h1 {{
            color: white;
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
        }}

        .card {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}

        .canvas-container {{
            background: #fafafa;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}

        .canvas-container svg {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            background: white;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}

        .info {{
            padding: 24px;
            text-align: center;
        }}

        .info h2 {{
            color: #1a1a1a;
            font-size: 1.5rem;
            margin-bottom: 8px;
        }}

        .info p {{
            color: #666;
            font-size: 1rem;
            margin-bottom: 24px;
        }}

        .cta {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            padding: 16px 32px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 1.1rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .cta:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
        }}

        .footer {{
            margin-top: 32px;
            text-align: center;
            color: rgba(255, 255, 255, 0.8);
            font-size: 0.9rem;
        }}

        .footer a {{
            color: white;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>🎨 Monet</h1>
        </div>

        <div class="card">
            <div class="canvas-container">
                <svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
                    <rect width="100%" height="100%" fill="#FFFFFF"/>
                    {svg_paths}
                </svg>
            </div>

            <div class="info">
                <h2>{title}</h2>
                <p>An AI-human collaboration created with Monet</p>
                <a href="{app_store_url}" class="cta">Get Monet Free</a>
            </div>
        </div>

        <div class="footer">
            <p>Create your own AI art collaborations</p>
            <p><a href="{app_store_url}">Download on the App Store</a></p>
        </div>
    </div>
</body>
</html>"""

    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "public, max-age=300",  # Cache for 5 minutes
        },
    )


@router.get("/{token}/api", response_model=dict[str, Any])
async def get_share_api(token: str) -> dict[str, Any]:
    """Get share metadata as JSON (for programmatic access, no auth required)."""
    share, strokes, _drawing_style, width, height = await load_shared_canvas(token)

    return {
        "token": share.token,
        "title": share.title or f"Artwork #{share.piece_number}",
        "piece_number": share.piece_number,
        "canvas_width": width,
        "canvas_height": height,
        "stroke_count": len(strokes),
        "created_at": share.created_at.isoformat(),
        "url": f"{settings.magic_link_base_url}/s/{share.token}",
        "preview_url": f"{settings.magic_link_base_url}/s/{share.token}/preview.png",
    }
