"""Naming tool for titling artwork."""

from __future__ import annotations

import logging
from typing import Any

from .context import ToolContext, ToolSpec

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 100


def normalize_title(raw: object) -> str | None:
    """The stored form of a name_piece title, or None if there is no usable title."""
    if not isinstance(raw, str):
        return None
    title = raw.strip()[:MAX_TITLE_LENGTH]
    return title or None


async def handle_name_piece(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Handle name_piece tool call.

    Generates a poetic title for the completed piece based on the canvas content.

    Args:
        args: Dictionary with 'title' - the chosen title for the piece

    Returns:
        Tool result confirming the title
    """
    title = normalize_title(args.get("title"))
    if title is None:
        return {
            "content": [{"type": "text", "text": "Error: Please provide a title for the piece"}],
            "is_error": True,
        }

    block_message = ctx.gate.finish_block_message()
    if block_message is not None:
        return {
            "content": [{"type": "text", "text": block_message}],
            "is_error": True,
        }

    # The calling agent's orchestrator stores and broadcasts the title from its
    # own tool-completion hook.

    # Build response
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f'🎨 This piece is now titled: "{title}"\n\n'
            "The title captures the essence of what you've created and will be "
            "saved with the piece in the gallery.",
        }
    ]

    return {"content": content}


name_piece = ToolSpec(
    "name_piece",
    """Give your completed piece a title.

Call this after signing, just before marking the piece done. A good title:
- Evokes the mood or essence of the work
- Can be poetic, abstract, or descriptive
- Becomes part of the piece's identity in the gallery

Examples of evocative titles:
- "Whispers at Dusk"
- "Convergence No. 7"
- "The Space Between"
- "Morning Light on Water"
- "Untitled (Blue Study)"

The title should feel inevitable—like it was always the name of this piece.""",
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The title for this piece. Be evocative and thoughtful.",
            },
        },
        "required": ["title"],
    },
    handle_name_piece,
)
