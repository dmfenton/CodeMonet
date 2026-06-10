"""Canvas critique tool for visual finish gates."""

from __future__ import annotations

import base64
import logging
from typing import Any

from anthropic import AsyncAnthropic
from claude_agent_sdk import tool

from code_monet.config import settings

from .callbacks import get_active_reference_png, get_canvas_callback
from .quality_gate import critique_gate_message, record_critique_result

logger = logging.getLogger(__name__)

CRITIQUE_PROMPT = """\
You are a strict painting critic for an autonomous artist. The first image is the
actual rendered canvas. Judge only what is visibly there. Do not reward intention.
Lead with failures. Be concrete and visual.

Critique like a painter, in this order:
1. Value structure: squint. Do two or three big light/dark masses read at thumbnail
   size, or does the image collapse into even mid-tone mush?
2. Composition: unequal intervals, a clear focal area, a route for the eye, and a
   counter-shape/negative space that keeps the dominant mass legible.
3. Subject: every required subject noun present and readable as a silhouette with
   ground contact — not a stick, dot, or disconnected mark.
4. Color: warm/cool relationships, shadows with color (not gray/black), a restrained
   high-chroma accent. Flat local-color filling is a failure.
5. Edges and marks: variety of hard/soft/lost edges, directional brushwork that
   describes form, no mechanical repetition, no accidental scaffold lines or long
   straight closure edges, no white canvas left by omission.
6. Finish: is anything overworked into noise, or unfinished where the eye lands?

Return this exact structure:
VERDICT: PASS or FAIL
FINDINGS:
- ...
REQUIRED_REVISIONS:
- ...

Use PASS only when the image is ready to sign. Do not pass a weak image because it
includes some required nouns. PASS requires the whole image to read at thumbnail size.
Required revisions must be structural and specific ("darken the foreground bank mass
and cut the river wedge lighter"), not decorative ("add more texture").
"""

REFERENCE_COMPARISON_NOTE = """\
The second image is the artist's own reference for this piece. The canvas is an
interpretation, not a copy — but compare the big things: value architecture, color
temperature and key, composition, and the presence of the subject. Call out the
largest divergences that weaken the canvas.
"""


def _image_block(png_bytes: bytes) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(png_bytes).decode("utf-8"),
        },
    }


async def handle_critique_canvas(args: dict[str, Any]) -> dict[str, Any]:
    """Critique the current canvas against a visual brief (and reference, if any)."""
    brief = args.get("brief", "")
    if not isinstance(brief, str) or not brief.strip():
        return {
            "content": [{"type": "text", "text": "Error: brief must be a non-empty string"}],
            "is_error": True,
        }

    get_canvas = get_canvas_callback()
    if get_canvas is None:
        return {
            "content": [{"type": "text", "text": "Error: Canvas not available"}],
            "is_error": True,
        }

    try:
        png_bytes = get_canvas()
    except Exception as e:
        logger.warning(f"Failed to render canvas for critique: {e}")
        return {
            "content": [{"type": "text", "text": f"Error: Failed to render canvas: {e}"}],
            "is_error": True,
        }

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = settings.agent_model if settings.dev_mode else settings.agent_model_prod

    content: list[Any] = [
        {"type": "text", "text": f"{CRITIQUE_PROMPT}\n\nBRIEF:\n{brief.strip()}"},
        _image_block(png_bytes),
    ]
    reference_png = get_active_reference_png()
    if reference_png is not None:
        content.append({"type": "text", "text": REFERENCE_COMPARISON_NOTE})
        content.append(_image_block(reference_png))

    response = await client.messages.create(
        model=model,
        max_tokens=900,
        temperature=0,
        messages=[{"role": "user", "content": content}],
    )

    text_parts = []
    for block in response.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            text_parts.append(text)
    critique = "\n".join(text_parts).strip()
    if not critique:
        critique = "VERDICT: FAIL\nFINDINGS:\n- Critique model returned no text.\nREQUIRED_REVISIONS:\n- Call view_canvas and revise manually."

    verdict = record_critique_result(critique)
    critique = f"{critique}\n\n{critique_gate_message(verdict)}"

    return {"content": [{"type": "text", "text": critique}]}


@tool(
    "critique_canvas",
    """Strictly critique the current rendered canvas against a visual brief. Use before signing any serious piece. Pass a concise brief listing required subject nouns, the intended value structure, focal area, palette/mood, and likely failure modes. If a reference image exists, the critic compares the canvas against it. If VERDICT is FAIL, revise before signing.""",
    {
        "type": "object",
        "properties": {
            "brief": {
                "type": "string",
                "description": "Concise visual brief and required pass criteria for the current piece.",
            }
        },
        "required": ["brief"],
    },
)
async def critique_canvas(args: dict[str, Any]) -> dict[str, Any]:
    """Critique the current canvas."""
    return await handle_critique_canvas(args)
