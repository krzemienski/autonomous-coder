"""EventHandler protocol and stream processing for SDK responses.

Adapts the SDK's streaming output (StreamEvent, AssistantMessage, ResultMessage)
into UI events consumable by both CLI and TUI adapters.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from claude_agent_sdk import AssistantMessage, ResultMessage
from claude_agent_sdk.types import StreamEvent

logger = logging.getLogger(__name__)


class EventHandler(Protocol):
    """Protocol for UI adapters. Both TUI and CLI implement this."""

    def on_text(self, text: str) -> None:
        """Incremental text chunk from Claude's response."""
        ...

    def on_tool_start(self, tool_name: str) -> None:
        """Claude is starting to call a tool."""
        ...

    def on_tool_input_chunk(self, json_chunk: str) -> None:
        """Incremental JSON input for the current tool call."""
        ...

    def on_tool_end(self) -> None:
        """Current tool call is complete."""
        ...

    def on_progress(self, phase: str, status: str, detail: str) -> None:
        """Phase progress update (from report_progress tool)."""
        ...

    def on_cost_update(self, total_cost: float, session_id: str) -> None:
        """Session cost update (from ResultMessage)."""
        ...

    def on_complete(self, result: str | None, success: bool) -> None:
        """Session finished."""
        ...


async def process_stream(
    client: Any,  # ClaudeSDKClient
    handler: EventHandler,
) -> ResultMessage | None:
    """Process the response stream, dispatching to the EventHandler.

    Returns the final ResultMessage for session metadata extraction.
    """
    in_tool = False
    final_result: ResultMessage | None = None

    async for msg in client.receive_response():
        match msg:
            case StreamEvent():
                event = msg.event
                event_type = event.get("type")

                if event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        in_tool = True
                        handler.on_tool_start(block.get("name", "unknown"))

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type")
                    if delta_type == "text_delta" and not in_tool:
                        handler.on_text(delta.get("text", ""))
                    elif delta_type == "input_json_delta" and in_tool:
                        handler.on_tool_input_chunk(delta.get("partial_json", ""))

                elif event_type == "content_block_stop":
                    if in_tool:
                        handler.on_tool_end()
                        in_tool = False

            case ResultMessage():
                final_result = msg
                cost = msg.total_cost_usd or 0.0
                handler.on_cost_update(cost, getattr(msg, "session_id", ""))
                handler.on_complete(
                    result=getattr(msg, "result", None),
                    success=not getattr(msg, "is_error", False),
                )

            case _:
                logger.debug("Unhandled message type: %s", type(msg).__name__)

    return final_result
