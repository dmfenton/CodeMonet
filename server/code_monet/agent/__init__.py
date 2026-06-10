"""Claude Agent with drawing tools using the Claude Agent SDK."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookMatcher,
)
from claude_agent_sdk.types import SyncHookJSONOutput

from code_monet.agent.callbacks import setup_tool_callbacks
from code_monet.agent.processor import (
    HookInput,
    HookInputOrDict,
    PostToolUseHookDict,
    extract_tool_name,
)

# Internal implementation - not part of public API
from code_monet.agent.processor import process_turn_messages as _process_turn_messages
from code_monet.agent.prompts import SYSTEM_PROMPT, build_system_prompt
from code_monet.agent.renderer import image_to_base64
from code_monet.config import settings
from code_monet.rendering import options_for_agent_view, render_strokes
from code_monet.tools import create_drawing_server
from code_monet.tools.callbacks import get_active_reference_png, set_active_reference
from code_monet.tools.quality_gate import (
    consume_mark_piece_done_accepted,
    quality_gate_prompt_context,
    reset_quality_gate,
)
from code_monet.types import (
    AgentEvent,
    AgentStatus,
    AgentTurnComplete,
    DrawingStyleConfig,
    DrawingStyleType,
    Path,
    get_style_config,
)

if TYPE_CHECKING:
    from code_monet.workspace import WorkspaceState


# Public exports (backward compat)
__all__ = [
    "DrawingAgent",
    "AgentCallbacks",
    "CodeExecutionResult",
    "ToolCallInfo",
    "SYSTEM_PROMPT",
    "build_system_prompt",
    "extract_tool_name",
    "HookInput",
    "HookInputOrDict",
    "PostToolUseHookDict",
]


@dataclass
class CodeExecutionResult:
    """Result of a code execution."""

    stdout: str
    stderr: str
    return_code: int
    iteration: int
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None


@dataclass
class ToolCallInfo:
    """Information about a tool call."""

    name: str  # Tool name (e.g., "draw_paths", "generate_svg")
    input: dict[str, Any] | None  # Tool input parameters
    iteration: int


@dataclass
class AgentCallbacks:
    """Callbacks for agent events."""

    on_thinking: Callable[[str, int], Coroutine[Any, Any, None]] | None = None
    on_iteration_start: Callable[[int, int], Coroutine[Any, Any, None]] | None = None
    on_code_start: Callable[[ToolCallInfo], Coroutine[Any, Any, None]] | None = None
    on_code_result: Callable[[CodeExecutionResult], Coroutine[Any, Any, None]] | None = None
    on_error: Callable[[str, str | None], Coroutine[Any, Any, None]] | None = None


logger = logging.getLogger(__name__)


class DrawingAgent:
    """Agent that generates drawings using the Claude Agent SDK.

    In multi-user mode, each user has their own DrawingAgent instance
    with an injected WorkspaceState.
    """

    def __init__(self, state: WorkspaceState | None = None) -> None:
        """Initialize the agent.

        Args:
            state: WorkspaceState for multi-user mode. If None, uses legacy singleton.
        """
        self._state = state
        self.pending_nudges: list[str] = []
        self._paused = True  # Start paused by default
        self._pause_lock = asyncio.Lock()
        self._abort = False  # Signal to abort current turn
        self._client: ClaudeSDKClient | None = None
        self._drawing_server = create_drawing_server()

        # Drawing hook support - orchestrator sets this callback
        self._on_draw: Callable[[list[Path]], Coroutine[Any, Any, None]] | None = None
        # Tool completion callback - orchestrator sets this to broadcast completed events
        self._on_tool_complete: (
            Callable[
                [str, dict[str, Any] | None, int, str | None, int | None], Coroutine[Any, Any, None]
            ]
            | None
        ) = None
        self._collected_paths: list[Path] = []
        self._piece_done = False
        # Track current iteration for tool completion callback
        self._current_iteration: int = 1

        # Track current style for session management
        self._current_style: DrawingStyleType | None = None

        # Build options (system prompt is set dynamically in _build_options)
        self._base_options: dict[str, Any] = {
            "mcp_servers": {"drawing": self._drawing_server},
            "allowed_tools": [
                # Drawing tools
                "mcp__drawing__draw_paths",
                "mcp__drawing__mark_piece_done",
                "mcp__drawing__generate_svg",
                "mcp__drawing__view_canvas",
                "mcp__drawing__critique_canvas",
                "mcp__drawing__imagine",
                "mcp__drawing__sign_canvas",
                "mcp__drawing__name_piece",
                # Filesystem tools (scoped to workspace via working_directory)
                "Read",
                "Write",
                "Glob",
                "Grep",
                "Bash",
            ],
            "permission_mode": "acceptEdits",
            "model": settings.agent_model if settings.dev_mode else settings.agent_model_prod,
            "include_partial_messages": True,
            "hooks": {"PostToolUse": [HookMatcher(hooks=[self._post_tool_use_hook])]},
            "env": {"ANTHROPIC_API_KEY": settings.anthropic_api_key},
        }

    def _build_options(
        self, style_type: DrawingStyleType, workspace_dir: str | None = None
    ) -> ClaudeAgentOptions:
        """Build agent options with style-specific system prompt.

        Args:
            style_type: The drawing style (PLOTTER or PAINT)
            workspace_dir: Optional workspace directory to scope filesystem tools
        """
        style_config = get_style_config(style_type)
        options = {
            "system_prompt": build_system_prompt(style_config),
            **self._base_options,
        }
        # Scope filesystem tools to user's workspace
        if workspace_dir:
            options["cwd"] = workspace_dir
        return ClaudeAgentOptions(**options)

    def get_style_config(self) -> DrawingStyleConfig:
        """Get the current drawing style configuration."""
        state = self.get_state()
        style_type = getattr(state.canvas, "drawing_style", DrawingStyleType.PLOTTER)
        return get_style_config(style_type)

    def set_on_draw(self, callback: Callable[[list[Path]], Coroutine[Any, Any, None]]) -> None:
        """Set the callback for drawing paths. Called by orchestrator."""
        self._on_draw = callback

    def set_on_tool_complete(
        self,
        callback: Callable[
            [str, dict[str, Any] | None, int, str | None, int | None],
            Coroutine[Any, Any, None],
        ],
    ) -> None:
        """Set the callback for tool completion. Called by orchestrator.

        Args:
            callback: Async function taking (tool_name, tool_input, iteration)
        """
        self._on_tool_complete = callback

    async def _post_tool_use_hook(
        self,
        input_data: HookInputOrDict,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> SyncHookJSONOutput:
        """PostToolUse hook - trigger drawing after draw_paths/generate_svg completes.

        The Claude Agent SDK passes a dict at runtime in Python, despite typed
        documentation suggesting objects. We use extract_tool_name() to handle both.
        """
        tool_name = extract_tool_name(input_data)
        # Extract tool_input from hook data
        tool_input: dict[str, Any] | None = None
        if isinstance(input_data, dict):
            raw_input = input_data.get("tool_input")
            if isinstance(raw_input, dict):
                tool_input = raw_input
        else:
            raw_input = getattr(input_data, "tool_input", None)
            if isinstance(raw_input, dict):
                tool_input = raw_input

        logger.info(f"PostToolUse: tool={tool_name}, collected_paths={len(self._collected_paths)}")

        # After drawing tools, execute drawing and wait
        if (
            tool_name
            in (
                "mcp__drawing__draw_paths",
                "mcp__drawing__generate_svg",
                "mcp__drawing__sign_canvas",
            )
            and self._collected_paths
        ):
            if self._on_draw:
                logger.info(f"PostToolUse: drawing {len(self._collected_paths)} paths")
                await self._on_draw(self._collected_paths.copy())
            self._collected_paths.clear()

        # After mark_piece_done, flag completion
        elif tool_name == "mcp__drawing__mark_piece_done":
            self._piece_done = consume_mark_piece_done_accepted()

        # Signal tool completion for all drawing tools (broadcasts "completed" message)
        # This unblocks client-side stroke rendering that waits for in-progress events to clear
        if self._on_tool_complete and tool_name.startswith("mcp__drawing__"):
            # Strip prefix for cleaner tool name (matches on_code_start format)
            clean_name = (
                tool_name[len("mcp__drawing__") :]
                if tool_name.startswith("mcp__drawing__")
                else tool_name
            )
            tool_response = _extract_hook_tool_response(input_data)
            stdout = _tool_response_text(tool_response)
            return_code = 1 if _tool_response_is_error(tool_response) else 0
            await self._on_tool_complete(
                clean_name,
                tool_input,
                self._current_iteration,
                stdout,
                return_code,
            )

        return SyncHookJSONOutput()

    def get_state(self) -> Any:
        """Get the workspace state (must be injected via constructor)."""
        if self._state is None:
            raise RuntimeError(
                "Agent state not initialized. Pass state to DrawingAgent constructor."
            )
        return self._state

    async def _save_state(self) -> None:
        """Save state (async for WorkspaceState, sync for StateManager)."""
        state = self.get_state()
        if hasattr(state, "save"):
            result = state.save()
            # If it's a coroutine (WorkspaceState), await it
            if asyncio.iscoroutine(result):
                await result

    @property
    def paused(self) -> bool:
        """Check if agent is paused (non-blocking read)."""
        return self._paused

    @property
    def container_id(self) -> str | None:
        """Container ID for backward compatibility (SDK manages sessions)."""
        return None

    def add_nudge(self, text: str) -> None:
        """Queue a nudge for the next agent turn."""
        self.pending_nudges.append(text)

    async def pause(self) -> None:
        """Pause the agent loop (thread-safe)."""
        async with self._pause_lock:
            self._paused = True

    async def resume(self) -> None:
        """Resume the agent loop (thread-safe)."""
        async with self._pause_lock:
            self._paused = False

    def reset_container(self) -> None:
        """Reset the session for a new piece."""
        self._abort = True  # Abort any running turn
        reset_quality_gate()
        set_active_reference(None)
        # Disconnect client to start fresh
        if self._client:
            client = self._client
            self._client = None
            asyncio.create_task(self._disconnect_client(client))

    async def _disconnect_client(self, client: ClaudeSDKClient | None = None) -> None:
        """Disconnect the client."""
        client_to_disconnect = client or self._client
        self._client = None
        if client_to_disconnect:
            try:
                await client_to_disconnect.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting client: {e}")

    async def _connect_client(
        self,
        style_type: DrawingStyleType,
        workspace_dir: str | None,
    ) -> None:
        """Connect a fresh SDK client, retrying once after SDK cleanup failures."""
        options = self._build_options(style_type, workspace_dir)
        last_error: Exception | None = None

        for attempt in range(2):
            client = ClaudeSDKClient(options=options)
            self._client = client
            try:
                await client.connect()
                return
            except Exception as e:
                last_error = e
                self._client = None
                with suppress(Exception):
                    await client.disconnect()
                if attempt == 0:
                    logger.warning("Agent client connect failed; retrying once", exc_info=True)

        if last_error is not None:
            raise last_error

    def _image_to_base64(self, img: Any) -> str:
        """Convert PIL Image to base64 string."""
        return image_to_base64(img)

    def _build_prompt(self) -> str:
        """Build the prompt with canvas context."""
        state = self.get_state()
        parts: list[str] = []

        # Canvas info
        parts.append(
            f"Canvas size: {state.canvas.width}x{state.canvas.height}\n"
            f"Existing strokes: {len(state.canvas.strokes)}\n"
            f"Piece number: {state.piece_number + 1}"
        )

        # Notes
        notes = state.notes
        if notes:
            parts.append(f"Your notes:\n{notes}")

        gate_context = quality_gate_prompt_context()
        if gate_context:
            parts.append(gate_context)

        # Nudges
        if self.pending_nudges:
            nudges_text = "\n".join(f"- {n}" for n in self.pending_nudges)
            parts.append(f"Human nudges:\n{nudges_text}")
            self.pending_nudges = []

        return "\n\n".join(parts)

    def _get_canvas_image(self, highlight_human: bool = True) -> Any:
        """Get canvas as PIL Image from current state.

        Renders paths using the active drawing style's colors and widths.
        In paint mode, applies brush expansion so the AI sees what users see.

        Note: This is a synchronous CPU-bound operation. Use _get_canvas_image_async
        when calling from async code to avoid blocking the event loop.
        """
        from dataclasses import replace

        state = self.get_state()
        canvas = state.canvas
        options = options_for_agent_view(canvas)
        if not highlight_human:
            options = replace(options, highlight_human=False)
        return render_strokes(canvas.strokes, options)

    async def _get_canvas_image_async(self, highlight_human: bool = True) -> Any:
        """Get canvas as PIL Image from current state (async, non-blocking).

        Offloads image rendering to thread pool to avoid blocking the event loop.
        """
        return await asyncio.to_thread(self._get_canvas_image, highlight_human)

    async def _build_multimodal_prompt(self) -> AsyncGenerator[dict[str, Any], None]:
        """Build prompt with text context and canvas image.

        Yields message dicts for the Claude SDK query:
        - User message with text and image content blocks
        """
        # Canvas image (non-blocking)
        img = await self._get_canvas_image_async(highlight_human=True)
        image_b64 = await asyncio.to_thread(self._image_to_base64, img)

        content = [
            {"type": "text", "text": self._build_prompt()},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64,
                },
            },
        ]

        # Keep the active reference visible every turn so the agent can
        # compare the canvas against it instead of recalling it from memory.
        reference_png = await asyncio.to_thread(get_active_reference_png)
        if reference_png is not None:
            content.append(
                {
                    "type": "text",
                    "text": (
                        "Your reference image for this piece (from imagine). Compare the "
                        "canvas above against it: value masses, color temperature, "
                        "composition, edges."
                    ),
                }
            )
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(reference_png).decode("utf-8"),
                    },
                }
            )

        yield {
            "type": "user",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
        }

    async def run_turn(
        self,
        callbacks: AgentCallbacks | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run a single agent turn.

        Drawing now happens via PostToolUse hook - no need to yield AgentPathsEvent.
        The hook calls _on_draw callback set by the orchestrator.

        Args:
            callbacks: Callbacks for various agent events

        Yields:
            AgentTurnComplete when the turn is finished
        """
        if self.paused:
            yield AgentTurnComplete(thinking="", done=False)
            return

        # Clear state at start of turn
        self._abort = False
        self._piece_done = False
        self._collected_paths.clear()
        state = self.get_state()

        cb = callbacks or AgentCallbacks()
        state.status = AgentStatus.THINKING
        await self._save_state()

        # Set up draw callback to collect paths for the PostToolUse hook (animation)
        async def on_draw(paths: list[Path], done: bool) -> None:
            self._collected_paths.extend(paths)
            if done:
                self._piece_done = True

        # Set up canvas callback for view_canvas tool
        def get_canvas_png() -> bytes:
            img = self._get_canvas_image(highlight_human=True)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

        # Set up callbacks
        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=state.canvas.width,
            canvas_height=state.canvas.height,
            on_paths_collected=on_draw,
        )

        try:
            # Connect client if needed
            if self._client is None:
                await self._connect_client(state.canvas.drawing_style, state.workspace_dir)
            client = self._client
            if client is None:
                raise RuntimeError("Agent client did not connect")

            # Send the turn prompt with canvas image
            await client.query(self._build_multimodal_prompt())

            # Track iteration for tool completion callback
            self._current_iteration = 1

            # Notify iteration start
            if cb.on_iteration_start:
                await cb.on_iteration_start(1, 1)

            # Process messages using the processor module
            result = await _process_turn_messages(
                client=client,
                callbacks=cb,
                is_aborted=lambda: self._abort,
                iteration=self._current_iteration,
            )

            # Handle abort
            if result.aborted:
                yield AgentTurnComplete(thinking=result.thinking, done=False)
                return

            # Update agent state
            state.monologue = result.thinking
            await self._save_state()

            # Note: piece_count increment and container reset are handled by
            # orchestrator.run_turn() which calls state.new_canvas() on piece completion

            # Signal turn complete
            yield AgentTurnComplete(thinking=result.thinking, done=self._piece_done)

        except Exception as e:
            logger.exception("Agent turn failed")
            self._client = None
            state.status = AgentStatus.ERROR
            await self._save_state()

            # Notify UI of error
            if cb.on_error:
                await cb.on_error(str(e), None)

            raise RuntimeError(f"Agent turn failed: {e}") from e


def _extract_hook_tool_response(input_data: HookInputOrDict) -> Any:
    """Extract PostToolUse response payload from SDK hook input."""
    if isinstance(input_data, dict):
        return input_data.get("tool_response")
    return getattr(input_data, "tool_response", None)


def _tool_response_is_error(response: Any) -> bool:
    """Return whether a hook tool response represents an execution error."""
    if isinstance(response, dict):
        return bool(response.get("is_error"))
    return bool(getattr(response, "is_error", False))


def _tool_response_text(response: Any) -> str | None:
    """Extract text content from a Claude SDK tool response payload."""
    if response is None:
        return None
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        content = response.get("content")
        if content is not None:
            return _tool_response_text(content)
        text = response.get("text")
        if isinstance(text, str):
            return text
        return None
    if isinstance(response, list):
        parts = [_tool_response_text(item) for item in response]
        joined = "\n".join(part for part in parts if part)
        return joined or None
    content = getattr(response, "content", None)
    if content is not None:
        return _tool_response_text(content)
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    return None
