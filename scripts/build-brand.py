"""Render Code Monet brand assets from brand/mark.svg.

Outputs (committed; rerun after changing the mark):
  ios/.../AppIcon.appiconset/AppIcon-1024.png       light app icon (opaque RGB)
  ios/.../AppIcon.appiconset/AppIcon-1024-dark.png  dark app icon (opaque RGB)
  ios/.../LaunchImage.imageset/LaunchImage@{2,3}x.png  launch mark, 120pt (transparent)
  web/public/favicon.svg                            browser tab icon
  web/public/apple-touch-icon.png                   home-screen icon
  web/public/og-image.png                           1200x630 social preview

Usage (from repo root):
  uv run --project server python scripts/build-brand.py
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MARK = ROOT / "brand" / "mark.svg"
ASSETS = ROOT / "ios" / "CodeMonet" / "Resources" / "Assets.xcassets"
PUBLIC = ROOT / "web" / "public"

FONTS = (
    "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400..600;"
    "1,9..144,400..500&family=IBM+Plex+Mono:wght@500&family=IBM+Plex+Sans:wght@400&display=swap"
)


def icon_html(mark: str, size: int, background: str, scale: float) -> str:
    inner = round(size * scale)
    return f"""<html><body style="margin:0">
<div style="width:{size}px;height:{size}px;background:{background};display:flex;
align-items:center;justify-content:center">
<div style="width:{inner}px;height:{inner}px">{mark}</div></div></body></html>"""


def og_html(mark: str) -> str:
    return f"""<html><head><link rel="stylesheet" href="{FONTS}"></head>
<body style="margin:0">
<div style="width:1200px;height:630px;background:#fdfbf5;color:#1a1d18;display:flex;
flex-direction:column;justify-content:space-between;padding:72px 84px;box-sizing:border-box;
font-family:'IBM Plex Sans',sans-serif">
  <div style="display:flex;align-items:center;gap:18px">
    <div style="width:84px;height:84px">{mark}</div>
    <div style="line-height:1">
      <div style="font:500 24px 'IBM Plex Mono',monospace;color:#1f4d34">code</div>
      <div style="font:italic 400 52px 'Fraunces',serif">Monet</div>
    </div>
  </div>
  <div>
    <div style="font:500 96px/1.02 'Fraunces',serif;letter-spacing:-0.02em">
      It paints by<br><em style="color:#1f4d34">writing code.</em></div>
    <div style="margin-top:28px;font-size:28px;color:#5e6358">
      An autonomous painter you can watch, stroke by stroke.</div>
  </div>
</div></body></html>"""


def render(
    page, html: str, width: int, height: int, *, transparent: bool = False
) -> Image.Image:
    page.set_viewport_size({"width": width, "height": height})
    page.set_content(html, wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    png = page.screenshot(
        omit_background=transparent,
        clip={"x": 0, "y": 0, "width": width, "height": height},
    )
    return Image.open(io.BytesIO(png))


def main() -> None:
    mark = MARK.read_text()
    icon_dir = ASSETS / "AppIcon.appiconset"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)
        render(page, icon_html(mark, 1024, "#f8f3e7", 0.88), 1024, 1024).convert(
            "RGB"
        ).save(icon_dir / "AppIcon-1024.png")
        render(page, icon_html(mark, 1024, "#15160f", 0.88), 1024, 1024).convert(
            "RGB"
        ).save(icon_dir / "AppIcon-1024-dark.png")
        for px, name in ((240, "LaunchImage@2x.png"), (360, "LaunchImage@3x.png")):
            render(
                page, icon_html(mark, px, "transparent", 1.0), px, px, transparent=True
            ).save(ASSETS / "LaunchImage.imageset" / name)
        render(page, icon_html(mark, 180, "#f8f3e7", 0.88), 180, 180).convert(
            "RGB"
        ).save(PUBLIC / "apple-touch-icon.png")
        render(page, og_html(mark), 1200, 630).convert("RGB").save(
            PUBLIC / "og-image.png"
        )
        browser.close()
    shutil.copyfile(MARK, PUBLIC / "favicon.svg")
    print("brand assets written")


if __name__ == "__main__":
    main()
