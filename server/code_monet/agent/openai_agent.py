"""OpenAI Responses API drawing agent.

This module intentionally mirrors the public surface of DrawingAgent so the
orchestrator can run either backend.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any

from openai import AsyncOpenAI

from code_monet.agent import AgentCallbacks, CodeExecutionResult, ToolCallInfo
from code_monet.agent.callbacks import setup_tool_callbacks
from code_monet.agent.prompts import build_system_prompt
from code_monet.agent.renderer import image_to_base64
from code_monet.config import settings
from code_monet.rendering import options_for_agent_view, render_strokes
from code_monet.tools import (
    handle_critique_canvas,
    handle_draw_paths,
    handle_generate_svg,
    handle_imagine,
    handle_mark_piece_done,
    handle_name_piece,
    handle_sign_canvas,
    handle_view_canvas,
)
from code_monet.tools.quality_gate import quality_gate_prompt_context, reset_quality_gate
from code_monet.types import (
    AgentEvent,
    AgentStatus,
    AgentTurnComplete,
    DrawingStyleConfig,
    DrawingStyleType,
    Path,
    get_style_config,
)

logger = logging.getLogger(__name__)


OPENAI_DRAWING_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "draw_paths",
        "description": "Draw path objects on the current canvas.",
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["line", "polyline", "quadratic", "cubic", "svg"],
                            },
                            "points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "x": {"type": "number"},
                                        "y": {"type": "number"},
                                    },
                                    "required": ["x", "y"],
                                    "additionalProperties": False,
                                },
                            },
                            "d": {"type": "string"},
                            "brush": {
                                "type": "string",
                                "enum": [
                                    "oil_round",
                                    "oil_flat",
                                    "oil_filbert",
                                    "watercolor",
                                    "dry_brush",
                                    "palette_knife",
                                    "ink",
                                    "pencil",
                                    "charcoal",
                                    "marker",
                                    "airbrush",
                                    "splatter",
                                ],
                            },
                            "color": {"type": "string"},
                            "stroke_width": {"type": "number"},
                            "opacity": {"type": "number"},
                            "fill": {"type": "string"},
                            "fill_opacity": {"type": "number"},
                        },
                        "required": ["type"],
                        "additionalProperties": False,
                    },
                },
                "done": {"type": "boolean"},
            },
            "required": ["paths"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "generate_svg",
        "description": "Run Python code that outputs SVG/path data for algorithmic drawings.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "done": {"type": "boolean"},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "view_canvas",
        "description": "Return the current canvas image.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "critique_canvas",
        "description": "Strictly critique the current rendered canvas against a visual brief.",
        "parameters": {
            "type": "object",
            "properties": {"brief": {"type": "string"}},
            "required": ["brief"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "sign_canvas",
        "description": "Add the Code Monet signature to the canvas.",
        "parameters": {
            "type": "object",
            "properties": {
                "position": {
                    "type": "string",
                    "enum": ["bottom_right", "bottom_left", "bottom_center"],
                },
                "size": {"type": "string", "enum": ["small", "medium", "large"]},
                "color": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "name_piece",
        "description": "Give the completed artwork a title.",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "mark_piece_done",
        "description": "Signal that the current piece is complete.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "imagine",
        "description": "Generate a reference image if GOOGLE_API_KEY is configured.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
]

for _tool in OPENAI_DRAWING_TOOLS:
    _tool["strict"] = False


class OpenAIDrawingAgent:
    """Drawing agent powered by the OpenAI Responses API."""

    def __init__(self, state: Any | None = None) -> None:
        self._state = state
        self.pending_nudges: list[str] = []
        self._paused = True
        self._pause_lock = asyncio.Lock()
        self._abort = False
        self._piece_done = False
        self._current_iteration = 1
        self._collected_paths: list[Path] = []
        self._client: AsyncOpenAI | None = None
        self._on_draw: Callable[[list[Path]], Coroutine[Any, Any, None]] | None = None
        self._on_tool_complete: (
            Callable[
                [str, dict[str, Any] | None, int, str | None, int | None], Coroutine[Any, Any, None]
            ]
            | None
        ) = None

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def container_id(self) -> str | None:
        return None

    def get_state(self) -> Any:
        if self._state is None:
            raise RuntimeError(
                "Agent state not initialized. Pass state to OpenAIDrawingAgent constructor."
            )
        return self._state

    def get_style_config(self) -> DrawingStyleConfig:
        state = self.get_state()
        style_type = getattr(state.canvas, "drawing_style", DrawingStyleType.PLOTTER)
        return get_style_config(style_type)

    def set_on_draw(self, callback: Callable[[list[Path]], Coroutine[Any, Any, None]]) -> None:
        self._on_draw = callback

    def set_on_tool_complete(
        self,
        callback: Callable[
            [str, dict[str, Any] | None, int, str | None, int | None],
            Coroutine[Any, Any, None],
        ],
    ) -> None:
        self._on_tool_complete = callback

    def add_nudge(self, text: str) -> None:
        self.pending_nudges.append(text)

    async def pause(self) -> None:
        async with self._pause_lock:
            self._paused = True

    async def resume(self) -> None:
        async with self._pause_lock:
            self._paused = False

    def reset_container(self) -> None:
        self._abort = True
        reset_quality_gate()

    async def _save_state(self) -> None:
        state = self.get_state()
        if hasattr(state, "save"):
            result = state.save()
            if asyncio.iscoroutine(result):
                await result

    def _image_to_base64(self, img: Any) -> str:
        return image_to_base64(img)

    def _build_prompt(self) -> str:
        state = self.get_state()
        parts = [
            f"Canvas size: {state.canvas.width}x{state.canvas.height}\n"
            f"Existing strokes: {len(state.canvas.strokes)}\n"
            f"Piece number: {state.piece_number + 1}"
        ]
        if state.notes:
            parts.append(f"Your notes:\n{state.notes}")
        gate_context = quality_gate_prompt_context()
        if gate_context:
            parts.append(gate_context)
        if self.pending_nudges:
            parts.append("Human nudges:\n" + "\n".join(f"- {n}" for n in self.pending_nudges))
            self.pending_nudges = []
        return "\n\n".join(parts)

    def _get_canvas_image(self, highlight_human: bool = True) -> Any:
        from dataclasses import replace

        canvas = self.get_state().canvas
        options = options_for_agent_view(canvas)
        if not highlight_human:
            options = replace(options, highlight_human=False)
        return render_strokes(canvas.strokes, options)

    async def _get_canvas_image_async(self, highlight_human: bool = True) -> Any:
        return await asyncio.to_thread(self._get_canvas_image, highlight_human)

    async def _build_input(self) -> list[dict[str, Any]]:
        img = await self._get_canvas_image_async(highlight_human=True)
        image_b64 = await asyncio.to_thread(self._image_to_base64, img)
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": self._build_prompt()},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_b64}",
                    },
                ],
            }
        ]

    async def _build_canvas_feedback_input(self) -> list[dict[str, Any]]:
        img = await self._get_canvas_image_async(highlight_human=True)
        image_b64 = await asyncio.to_thread(self._image_to_base64, img)
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Updated canvas after the tool call. Continue from this state.",
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_b64}",
                    },
                ],
            }
        ]

    async def _flush_collected_paths(self) -> None:
        if self._collected_paths and self._on_draw:
            await self._on_draw(self._collected_paths.copy())
        self._collected_paths.clear()

    async def _run_tool(
        self,
        name: str,
        args: dict[str, Any],
        callbacks: AgentCallbacks,
    ) -> dict[str, Any]:
        if callbacks.on_code_start:
            await callbacks.on_code_start(
                ToolCallInfo(name=name, input=args, iteration=self._current_iteration)
            )

        handlers = {
            "draw_paths": handle_draw_paths,
            "generate_svg": handle_generate_svg,
            "view_canvas": lambda _args: handle_view_canvas(),
            "critique_canvas": handle_critique_canvas,
            "sign_canvas": handle_sign_canvas,
            "name_piece": handle_name_piece,
            "mark_piece_done": lambda _args: handle_mark_piece_done(),
            "imagine": handle_imagine,
        }
        handler = handlers.get(name)
        if handler is None:
            result = {
                "content": [{"type": "text", "text": f"Error: unknown tool {name}"}],
                "is_error": True,
            }
        else:
            result = await handler(args)

        await self._flush_collected_paths()
        if not result.get("is_error") and (
            name == "mark_piece_done" or (name == "draw_paths" and args.get("done"))
        ):
            self._piece_done = True
        if not result.get("is_error") and name == "generate_svg" and args.get("done"):
            self._piece_done = True

        return_code = 1 if result.get("is_error") else 0
        if callbacks.on_code_result:
            await callbacks.on_code_result(
                CodeExecutionResult(
                    stdout=_tool_result_text(result),
                    stderr="" if return_code == 0 else _tool_result_text(result),
                    return_code=return_code,
                    iteration=self._current_iteration,
                    tool_name=name,
                    tool_input=args,
                )
            )
        if self._on_tool_complete:
            await self._on_tool_complete(
                name,
                args,
                self._current_iteration,
                _tool_result_text(result),
                return_code,
            )
        return result

    async def run_turn(
        self,
        callbacks: AgentCallbacks | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        if self.paused:
            yield AgentTurnComplete(thinking="", done=False)
            return
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when AGENT_PROVIDER=openai")
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)

        self._abort = False
        self._piece_done = False
        self._collected_paths.clear()
        state = self.get_state()
        cb = callbacks or AgentCallbacks()
        state.status = AgentStatus.THINKING
        await self._save_state()

        async def on_draw(paths: list[Path], done: bool) -> None:
            self._collected_paths.extend(paths)
            if done:
                self._piece_done = True

        def get_canvas_png() -> bytes:
            img = self._get_canvas_image(highlight_human=True)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=state.canvas.width,
            canvas_height=state.canvas.height,
            on_paths_collected=on_draw,
        )

        thinking_text = ""
        model = (
            settings.openai_agent_model if settings.dev_mode else settings.openai_agent_model_prod
        )
        input_items = await self._build_input()
        previous_response_id: str | None = None

        for iteration in range(1, settings.max_agent_iterations + 1):
            if self._abort:
                yield AgentTurnComplete(thinking=thinking_text, done=False)
                return
            self._current_iteration = iteration
            if cb.on_iteration_start:
                await cb.on_iteration_start(iteration, settings.max_agent_iterations)

            request: dict[str, Any] = {
                "model": model,
                "instructions": build_system_prompt(get_style_config(state.canvas.drawing_style)),
                "input": input_items,
                "tools": OPENAI_DRAWING_TOOLS,
            }
            if previous_response_id:
                request["previous_response_id"] = previous_response_id
            response = await self._client.responses.create(**request)
            previous_response_id = str(response.id)
            text = getattr(response, "output_text", "") or ""
            if text:
                thinking_text += text
                if cb.on_thinking:
                    await cb.on_thinking(text, iteration)

            tool_outputs = []
            for call in _response_function_calls(response):
                args = _decode_tool_args(call.get("arguments"))
                result = await self._run_tool(call["name"], args, cb)
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(_openai_tool_output(result)),
                    }
                )

            if not tool_outputs:
                break
            input_items = tool_outputs + await self._build_canvas_feedback_input()

        state.monologue = thinking_text
        await self._save_state()
        yield AgentTurnComplete(thinking=thinking_text, done=self._piece_done)


def _response_function_calls(response: Any) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None)
        if item_type != "function_call":
            continue
        call_id = getattr(item, "call_id", None)
        name = getattr(item, "name", None)
        if not call_id or not name:
            continue
        calls.append(
            {
                "call_id": str(call_id),
                "name": str(name),
                "arguments": str(getattr(item, "arguments", "{}") or "{}"),
            }
        )
    return calls


def _decode_tool_args(raw_args: str | None) -> dict[str, Any]:
    if not raw_args:
        return {}
    try:
        decoded = json.loads(raw_args)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _tool_result_text(result: dict[str, Any]) -> str:
    text_parts = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            text_parts.append(str(item.get("text", "")))
    return "\n".join(part for part in text_parts if part)


def _openai_tool_output(result: dict[str, Any]) -> dict[str, Any]:
    content = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            content.append(item)
    return {"content": content, "is_error": bool(result.get("is_error", False))}
