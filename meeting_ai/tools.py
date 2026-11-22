"""Registered read-only tools for channel questions."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

HISTORY_TOOL_NAME = "get_current_channel_history"
HISTORY_LIMIT = 100
HISTORY_CHAR_LIMIT = 12_000

ReadHistory = Callable[[], Awaitable[Sequence[Mapping[str, Any]]]]


class ToolArguments(BaseModel):
    """Base for strict OpenAI schemas and server-side argument validation."""

    model_config = ConfigDict(extra="forbid", strict=True)


@dataclass(frozen=True)
class ToolContext:
    """Discord-scoped operations supplied by the handler, outside model control."""

    read_history: ReadHistory


@dataclass(frozen=True)
class Tool:
    description: str
    arguments: type[ToolArguments]
    handler: Callable[[ToolContext, Any], Awaitable[dict]]

    def definition(self, name: str) -> dict:
        return {
            "type": "function",
            "name": name,
            "description": self.description,
            "parameters": self.arguments.model_json_schema(),
            "strict": True,
        }


class InvalidToolCall(ValueError):
    """The model requested an unknown tool or supplied invalid arguments."""


async def get_current_channel_history(context: ToolContext, _args: ToolArguments) -> dict:
    """Return the latest authorized messages, ordered oldest first for the model."""
    rows = await context.read_history()
    messages = []
    remaining = HISTORY_CHAR_LIMIT
    truncated = False
    for row in reversed(rows[-HISTORY_LIMIT:]):
        content = row["content"].strip()
        if not content:
            continue
        if not remaining:
            truncated = True
            break
        messages.append({
            "message_id": str(row["message_id"]),
            "user_id": str(row["user_id"]),
            "created_at": row["created_at"],
            "content": content[:remaining],
        })
        truncated |= len(content) > remaining
        remaining -= len(messages[-1]["content"])
    return {"messages": messages[::-1], "truncated": truncated}


TOOLS = {
    HISTORY_TOOL_NAME: Tool(
        "讀取目前 Discord 頻道最近保存的歷史文字，可用來回答討論內容、決定或頻道摘要。",
        ToolArguments,
        get_current_channel_history,
    ),
}


async def execute_tool(name: str, arguments: str, context: ToolContext) -> dict:
    """Validate a model request before executing an explicitly registered handler."""
    tool = TOOLS.get(name)
    if tool is None:
        raise InvalidToolCall("Unknown tool")
    try:
        params = tool.arguments.model_validate_json(arguments)
    except ValidationError as exc:
        raise InvalidToolCall("Invalid tool arguments") from exc
    return await tool.handler(context, params)
