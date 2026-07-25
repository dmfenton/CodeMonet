"""Image generation tool using Gemini API."""

from __future__ import annotations

import asyncio
import logging
import time
from io import BytesIO
from pathlib import Path as FilePath
from typing import Any

from claude_agent_sdk import tool

from .callbacks import get_workspace_dir_callback, image_content_from_png, set_active_reference

logger = logging.getLogger(__name__)

# Image generation timeout (seconds)
IMAGE_GEN_TIMEOUT = 60
REFERENCE_PREVIEW_MAX_SIZE = 512


async def handle_imagine(args: dict[str, Any]) -> dict[str, Any]:
    """Handle imagine tool call.

    Generates an image using Google's Nano Banana (Gemini image generation),
    saves it to the workspace, and returns it to the agent.

    Args:
        args: Dictionary with 'prompt' (required) and optional 'name' for the file

    Returns:
        Tool result with the generated image and file path
    """
    from code_monet.config import settings

    prompt = args.get("prompt", "")
    name = args.get("name", "")

    if not prompt or not isinstance(prompt, str):
        return {
            "content": [{"type": "text", "text": "Error: prompt must be a non-empty string"}],
            "is_error": True,
        }

    if not settings.google_api_key:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Error: Image generation not available. GOOGLE_API_KEY not configured.",
                }
            ],
            "is_error": True,
        }

    _get_workspace_dir_callback = get_workspace_dir_callback()
    if _get_workspace_dir_callback is None:
        return {
            "content": [{"type": "text", "text": "Error: Workspace not available"}],
            "is_error": True,
        }

    try:
        from google import genai
        from PIL import Image

        # Initialize client with API key
        client = genai.Client(api_key=settings.google_api_key)

        # Generate image using Nano Banana (Flash model)
        logger.info(f"Generating image with prompt: {prompt[:100]}...")

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model="gemini-2.5-flash-image",
                    contents=prompt,
                ),
                timeout=IMAGE_GEN_TIMEOUT,
            )
        except TimeoutError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Image generation timed out after {IMAGE_GEN_TIMEOUT}s",
                    }
                ],
                "is_error": True,
            }

        # Check for valid response
        if not response.candidates or len(response.candidates) == 0:
            return {
                "content": [
                    {"type": "text", "text": "Error: No response from image generation API"}
                ],
                "is_error": True,
            }

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            return {
                "content": [{"type": "text", "text": "Error: Empty response from API"}],
                "is_error": True,
            }

        # Process response
        image_data = None
        text_response = None

        for part in candidate.content.parts:
            if part.text is not None:
                text_response = part.text
            elif part.inline_data is not None:
                image_data = part.inline_data.data

        if image_data is None:
            error_msg = "No image generated."
            if text_response:
                error_msg += f" Model response: {text_response}"
            return {
                "content": [{"type": "text", "text": f"Error: {error_msg}"}],
                "is_error": True,
            }

        # Load image and save to workspace
        image = Image.open(BytesIO(image_data))
        workspace_dir = _get_workspace_dir_callback()
        references_dir = FilePath(workspace_dir) / "references"
        references_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        if name:
            # Sanitize the name
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
            filename = f"{safe_name}.png"
        else:
            # Generate a unique name based on timestamp
            filename = f"reference_{int(time.time())}.png"

        filepath = references_dir / filename
        image.save(filepath, "PNG")
        set_active_reference(str(filepath))

        logger.info(f"Saved generated image to {filepath}")

        preview = image.copy()
        preview.thumbnail(
            (REFERENCE_PREVIEW_MAX_SIZE, REFERENCE_PREVIEW_MAX_SIZE),
            Image.Resampling.LANCZOS,
        )
        image_buffer = BytesIO()
        preview.save(image_buffer, "PNG", optimize=True)

        # Build response
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"Generated full-size image saved to references/{filename}. "
                f"Returned a {REFERENCE_PREVIEW_MAX_SIZE}px preview; "
                "view the saved file with Read if you need the full image.",
            }
        ]

        # Add model's text response if any
        if text_response:
            content.append({"type": "text", "text": f"Model notes: {text_response}"})

        # Include the image in response
        content.append(image_content_from_png(image_buffer.getvalue()))

        return {"content": content}

    except Exception as e:
        logger.exception(f"Image generation failed: {e}")
        return {
            "content": [{"type": "text", "text": f"Error generating image: {e!s}"}],
            "is_error": True,
        }


@tool(
    "imagine",
    """Generate a reference image using AI (Nano Banana / Google Gemini).

Use this to create reference images for your drawings - visual inspiration, style references,
or to visualize what you're trying to create before drawing it.

The generated image is saved to your workspace and returned so you can see it immediately.
You can view saved reference images later using the Read tool on the references/ directory.

Tips for good prompts:
- Be specific about subject, style, composition, and mood
- Use photographic terms like "wide angle", "close-up", "soft lighting"
- Specify art styles if relevant: "watercolor style", "line art", "minimalist"

Example prompts:
- "A serene Japanese garden with cherry blossoms at sunset, soft lighting"
- "Simple line drawing of a cat sitting, minimal black lines on white"
- "Abstract geometric pattern with overlapping circles in blue and orange"
""",
    {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the image to generate",
            },
            "name": {
                "type": "string",
                "description": "Optional name for the image file (without extension). If not provided, a timestamp-based name is used.",
            },
        },
        "required": ["prompt"],
    },
)
async def imagine(args: dict[str, Any]) -> dict[str, Any]:
    """Generate a reference image using AI."""
    return await handle_imagine(args)
