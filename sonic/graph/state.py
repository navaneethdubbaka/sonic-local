from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class TurnState(TypedDict):
    utterance: str
    foreground_window: str
    history: list[dict[str, str]]
    route: NotRequired[str]
    risk: NotRequired[str]
    needs_tool: NotRequired[str]
    complexity: NotRequired[str]
    route_confidence: NotRequired[float]
    next_node: NotRequired[str]
    model_used: NotRequired[str]
    tool_calls: NotRequired[list[dict[str, Any]]]
    confidence: NotRequired[float | None]
    result_text: NotRequired[str]
    error: NotRequired[str | None]
    cloud_called: NotRequired[bool]
    laya_runtime: NotRequired[str]
    laya_provider: NotRequired[str]
    mode: NotRequired[Literal["continuous", "autonomous"]]
