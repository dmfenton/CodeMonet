"""Canvas critique tool for visual finish gates."""

from __future__ import annotations

import base64
import logging
from typing import Any

from anthropic import AsyncAnthropic
from claude_agent_sdk import tool

from code_monet.config import settings

from .callbacks import get_canvas_callback
from .quality_gate import critique_gate_message, record_critique_result

logger = logging.getLogger(__name__)

CRITIQUE_PROMPT = """\
You are a strict visual critic for an autonomous drawing agent.

Judge only the actual rendered image against the supplied brief. Do not reward intention.
Lead with failures. Be concrete and visual.

Return this exact structure:
VERDICT: PASS or FAIL
FINDINGS:
- ...
REQUIRED_REVISIONS:
- ...

Use PASS only when the image is ready to sign.

Mandatory FAIL conditions:
- The dominant shape reads as a simple dome, cap, mound, rectangle, blob, or generic helper template
  instead of the requested reference silhouette. An arched body is allowed only when the requested
  visual family actually needs one and the separate lip, underside, and counter-shape still read.
- A requested curl, tunnel, opening, bite, cutout, hole, or counter-shape is weak, merely implied,
  or hidden inside a broad solid mass.
- A requested small figure/object is only a stick annotation, dot, or disconnected mark.
- A requested prop/vehicle/tool/board/object is too thin, detached, or unreadable at thumbnail scale.
- Lower/foreground structure is missing where the brief requires ground, water, wake, shadow,
  reflection, texture, or directional marks.
- Accidental scaffold lines, long closure edges, blocky helper shapes, or unrelated geometric
  bands dominate the composition.

Do not pass a weak image because it includes some required nouns. PASS requires the whole image
to read correctly at thumbnail size.
"""


async def handle_critique_canvas(args: dict[str, Any]) -> dict[str, Any]:
    """Critique the current canvas against a visual brief."""
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
    image_data = base64.standard_b64encode(png_bytes).decode("utf-8")
    model = settings.agent_model if settings.dev_mode else settings.agent_model_prod

    response = await client.messages.create(
        model=model,
        max_tokens=900,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{CRITIQUE_PROMPT}\n\nBRIEF:\n{brief.strip()}"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    },
                ],
            }
        ],
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
    """Strictly critique the current rendered canvas against a visual brief. Use before signing reference work, small assets, or any piece where visual fidelity matters. Pass a concise brief listing required subject nouns, dominant silhouette, counter-shape, focal anchor, lower/foreground requirements, style grammar, and failure modes. If VERDICT is FAIL, revise before signing.""",
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
