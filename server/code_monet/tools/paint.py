"""paint tool: run the painting program and show the agent the rendered version."""

from __future__ import annotations

from typing import Any

from code_monet.program_painting import PaintFailure, PaintSuccess

from .context import ToolContext, ToolSpec, image_content_from_png


async def handle_paint(ctx: ToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    """Run studio/painting.py; return the rendered image or the program's error."""
    if ctx.paint is None:
        return {
            "content": [{"type": "text", "text": "Error: painting studio unavailable"}],
            "is_error": True,
        }

    result = await ctx.paint()
    match result:
        case PaintFailure(error=error, seconds=seconds):
            return {
                "content": [{"type": "text", "text": f"{error}\n(ran {seconds:.1f}s)"}],
                "is_error": True,
            }
        case PaintSuccess(version=v, preview=preview, seconds=seconds):
            text = (
                f"Version {v.version} rendered in {seconds:.1f}s — {v.ops} recorded marks, "
                f"stages: {', '.join(v.stages) or '(none)'}. Viewers are watching it paint in now.\n"
                f"Full resolution ({v.image_width}x{v.image_height}): paintings/{v.token}/final.png "
                "(use Read on it, or crop it with Bash, to inspect detail).\n"
                "Look hard at the image below before changing anything."
            )
            return {
                "content": [
                    {"type": "text", "text": text},
                    image_content_from_png(preview.read_bytes()),
                ]
            }


paint = ToolSpec(
    "paint",
    """Run your painting program (studio/painting.py) and see the result.

The program paints on a ready `cv` canvas (paintlib) — see the system prompt for the API.
Each successful run becomes a new version of the painting that viewers watch paint in,
stage by stage. Returns the rendered image, or the program's traceback on error.
Edit the program with Write/Edit, then call paint again.""",
    {},
    handle_paint,
)
