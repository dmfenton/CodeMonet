"""Naming tool for titling artwork."""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import tool

from .callbacks import get_piece_title_callback
from .quality_gate import finish_block_message

logger = logging.getLogger(__name__)


async def handle_name_piece(args: dict[str, Any]) -> dict[str, Any]:
    """Handle name_piece tool call.

    Generates a poetic title for the completed piece based on the canvas content.

    Args:
        args: Dictionary with 'title' - the chosen title for the piece

    Returns:
        Tool result confirming the title
    """
    title = args.get("title", "")

    if not title or not isinstance(title, str):
        return {
            "content": [{"type": "text", "text": "Error: Please provide a title for the piece"}],
            "is_error": True,
        }

    block_message = finish_block_message()
    if block_message is not None:
        return {
            "content": [{"type": "text", "text": block_message}],
            "is_error": True,
        }

    # Clean up the title
    title = title.strip()
    if len(title) > 100:
        title = title[:100]

    # Store the title via callback if available
    _set_piece_title_callback = get_piece_title_callback()
    if _set_piece_title_callback is not None:
        try:
            await _set_piece_title_callback(title)
            logger.info(f"Piece titled: {title}")
        except Exception as e:
            logger.warning(f"Failed to save piece title: {e}")

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


@tool(
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
)
async def name_piece(args: dict[str, Any]) -> dict[str, Any]:
    """Give the piece a title."""
    return await handle_name_piece(args)
