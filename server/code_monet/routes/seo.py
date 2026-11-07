"""SEO endpoints: sitemap and robots.txt."""

from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter
from fastapi.responses import Response

from code_monet.routes.public_gallery import public_piece_records

router = APIRouter()

SITE_URL = "https://monet.dmfenton.net"


def sitemap_xml(records: list[tuple[str, str, dict[str, Any]]]) -> str:
    """The sitemap for the homepage, the gallery and every public piece."""
    urls: list[dict[str, Any]] = [
        {"loc": f"{SITE_URL}/", "priority": "1.0", "changefreq": "daily"},
        {"loc": f"{SITE_URL}/gallery", "priority": "0.8", "changefreq": "daily"},
    ]
    for user_id, piece_id, data in records:
        url_entry: dict[str, Any] = {
            "loc": f"{SITE_URL}/gallery/{user_id}/{piece_id}",
            "priority": "0.6",
            "changefreq": "monthly",
        }
        created_at = data.get("created_at", "")
        if isinstance(created_at, str) and created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                url_entry["lastmod"] = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        urls.append(url_entry)

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        xml_parts.append("  <url>")
        xml_parts.append(f"    <loc>{escape(url['loc'])}</loc>")
        if "lastmod" in url:
            xml_parts.append(f"    <lastmod>{url['lastmod']}</lastmod>")
        xml_parts.append(f"    <changefreq>{url['changefreq']}</changefreq>")
        xml_parts.append(f"    <priority>{url['priority']}</priority>")
        xml_parts.append("  </url>")
    xml_parts.append("</urlset>")
    return "\n".join(xml_parts) + "\n"


@router.get("/sitemap.xml")
async def get_sitemap() -> Response:
    """The same sitemap the pre-rendered site publishes at /sitemap.xml."""
    return Response(content=sitemap_xml(await public_piece_records()), media_type="application/xml")


@router.get("/robots.txt")
async def get_robots_txt() -> Response:
    """Serve robots.txt for search engine crawlers."""
    content = """# Code Monet - AI Artist
User-agent: *
Allow: /
Allow: /gallery/
Allow: /public/

# Sitemap location
Sitemap: https://monet.dmfenton.net/sitemap.xml

# Private routes
Disallow: /studio
Disallow: /auth/
Disallow: /api/
Disallow: /ws
Disallow: /debug/
"""
    return Response(content=content, media_type="text/plain")
