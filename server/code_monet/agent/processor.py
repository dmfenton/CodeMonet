"""SDK message processing loop for the drawing agent."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias, TypedDict

from claude_agent_sdk import (
    AssistantMessage,
    HookInput,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import StreamEvent

if TYPE_CHECKING:
    from code_monet.agent import AgentCallbacks


logger = logging.getLogger(__name__)


class PostToolUseHookDict(TypedDict, total=False):
    """Dict structure the Claude Agent SDK passes to PostToolUse hooks in Python.

    The SDK documentation shows typed classes, but at runtime Python receives dicts.
    """

    hook_event_name: str
    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_response: Any


# Union of possible input types for hooks (dict at runtime, typed for static analysis)
HookInputOrDict: TypeAlias = HookInput | PostToolUseHookDict | dict[str, Any]


def extract_tool_name(input_data: HookInputOrDict) -> str:
    """Extract tool_name from hook input, handling both dict and object forms.

    The Claude Agent SDK passes dicts in Python, but types suggest objects.
    This helper safely extracts tool_name from either form.

    Args:
        input_data: Hook input data (dict or typed object)

    Returns:
        The tool name, or empty string if not found
    """
    if isinstance(input_data, dict):
        return str(input_data.get("tool_name", "") or "")
    return str(getattr(input_data, "tool_name", "") or "")


@dataclass
class TurnResult:
    """Result of processing a turn's messages."""

    thinking: str
    aborted: bool


async def process_turn_messages(
    client: Any,  # ClaudeSDKClient - avoid import cycle
    callbacks: AgentCallbacks,
    is_aborted: Callable[[], bool],
    iteration: int = 1,
) -> TurnResult:
    """Process all messages from an SDK turn response.

    Handles streaming events, tool calls, and results.

    Args:
        client: The Claude SDK client
        callbacks: Callbacks for agent events
        is_aborted: Function that returns True if turn should abort
        iteration: Current iteration number

    Returns:
        TurnResult with accumulated thinking and completion status
    """
    # Import here to avoid circular dependency
    from code_monet.agent import CodeExecutionResult, ToolCallInfo

    all_thinking = ""
    last_tool_name: str | None = None
    last_tool_input: dict[str, Any] | None = None

    async for message in client.receive_response():
        # Check for abort
        if is_aborted():
            logger.info("Turn aborted - new canvas requested")
            return TurnResult(thinking=all_thinking, aborted=True)

        if isinstance(message, StreamEvent):
            # Handle streaming events for real-time text
            event = message.event
            event_type = event.get("type", "")

            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text and callbacks.on_thinking:
                        all_thinking += text
                        await callbacks.on_thinking(text, iteration)

        elif isinstance(message, AssistantMessage):
            # Complete message - handle tool blocks only
            # Text is already sent via streaming (content_block_delta), don't duplicate
            for block in message.content:
                if isinstance(block, TextBlock):
                    # Text was already streamed via content_block_delta events
                    # Only update all_thinking if it wasn't captured during streaming
                    # (e.g., if streaming was interrupted or incomplete)
                    text = block.text
                    if (
                        text
                        and all_thinking
                        and not all_thinking.endswith(text)
                        and text not in all_thinking
                    ):
                        # This is new text that wasn't streamed - rare edge case
                        logger.debug(f"Non-streamed text block: {len(text)} chars")
                        all_thinking += text
                        if callbacks.on_thinking:
                            await callbacks.on_thinking(text, iteration)
                    elif text and not all_thinking:
                        # No streaming happened at all, use full text
                        all_thinking = text
                        if callbacks.on_thinking:
                            await callbacks.on_thinking(text, iteration)

                elif isinstance(block, ToolUseBlock):
                    # Tool being called - drawing happens in PostToolUse hook
                    # Extract friendly tool name (remove mcp__drawing__ prefix)
                    tool_name = block.name
                    if tool_name.startswith("mcp__drawing__"):
                        tool_name = tool_name[len("mcp__drawing__") :]
                    logger.info(f"Tool use: {tool_name}")
                    # Track tool info for pairing with result
                    last_tool_name = tool_name
                    last_tool_input = block.input if hasattr(block, "input") else None
                    if callbacks.on_code_start:
                        tool_info = ToolCallInfo(
                            name=tool_name,
                            input=last_tool_input,
                            iteration=iteration,
                        )
                        await callbacks.on_code_start(tool_info)

                elif isinstance(block, ToolResultBlock):
                    # Tool result - pair with last tool call
                    content = block.content if block.content else ""
                    if callbacks.on_code_result:
                        await callbacks.on_code_result(
                            CodeExecutionResult(
                                stdout=str(content),
                                stderr="",
                                return_code=1 if block.is_error else 0,
                                iteration=iteration,
                                tool_name=last_tool_name,
                                tool_input=last_tool_input,
                            )
                        )
                    # Clear tracked tool after result
                    last_tool_name = None
                    last_tool_input = None

        elif isinstance(message, SystemMessage):
            logger.debug(f"System message: {message.subtype}")

        elif isinstance(message, ResultMessage):
            # Turn complete
            logger.info(f"Turn complete: {message.subtype}")
            if message.is_error and callbacks.on_error:
                await callbacks.on_error(message.result or "Unknown error", None)

    return TurnResult(thinking=all_thinking, aborted=False)
