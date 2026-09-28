from __future__ import annotations

from typing import Any, Literal

RouteName = Literal[
    "desktop",
    "browser",
    "web_search",
    "google",
    "cloud_answer",
    "clarify",
    "calculator",
    "refuse",
]

RiskName = Literal["observe", "confirm", "refuse"]
NeedsTool = Literal["tool", "prose"]
Complexity = Literal["single_step", "multi_step", "open_reasoning"]

ROUTE_CRITERIA: dict[str, str] = {
    "desktop": (
        "open an app, focus a window, click a button, type into a field, "
        "or press keys on this computer"
    ),
    "browser": (
        "drive a web page by clicking or filling forms in Chrome, "
        "or complete a multi-step website goal"
    ),
    "web_search": (
        "look up a fact on the web with a search query, without operating a page"
    ),
    "google": (
        "read the user's Google Calendar, Gmail, or Drive through Google APIs"
    ),
    "cloud_answer": (
        "answer a general question, explain something, compare ideas, "
        "or write composed text that is not a PC action"
    ),
    "clarify": (
        "the request is incomplete, ambiguous, or missing a required detail"
    ),
}

RISK_CRITERIA = [
    "observe only, no side effect",
    "ask the user to confirm before acting",
    "refuse: purchase, send mail, delete, change password, or disable security",
]

NEEDS_TOOL_CRITERIA = {
    "tool": "the user wants the computer to take an action or fetch account data",
    "prose": "the user wants a spoken or written answer only",
}

COMPLEXITY_CRITERIA = [
    "one simple action or short answer",
    "several steps or tools",
    "open reasoning, long explanation, or careful analysis",
]


def routing_questions() -> dict[str, Any]:
    return {
        "route": {
            "type": "choice",
            "instructions": (
                "Which path should handle this user request on a Windows PC assistant?"
            ),
            "criteria": ROUTE_CRITERIA,
        },
        "risk": {
            "type": "score",
            "instructions": "How risky is fulfilling this request?",
            "criteria": RISK_CRITERIA,
        },
        "needs_tool": {
            "type": "choice",
            "instructions": "Does this request require a tool call?",
            "criteria": NEEDS_TOOL_CRITERIA,
        },
        "complexity": {
            "type": "score",
            "instructions": "How complex is this request?",
            "criteria": COMPLEXITY_CRITERIA,
        },
    }


def build_laya_state(
    utterance: str,
    *,
    foreground_window: str = "",
    tool_groups: list[str] | None = None,
) -> str:
    groups = tool_groups or ["desktop", "web_search", "google", "browser"]
    window = foreground_window or "(unknown)"
    return (
        f"User request: {utterance}\n"
        f"Foreground window: {window}\n"
        f"Available tool groups: {', '.join(groups)}\n"
        "Decide the single best path for a Windows PC assistant."
    )


ROUTE_TO_NODE: dict[str, str] = {
    "desktop": "needle_desktop",
    "browser": "browser_graph",
    "web_search": "needle_search",
    "google": "needle_google",
    "cloud_answer": "cloud_chat",
    "clarify": "ask_user",
    "calculator": "calculator",
    "refuse": "refuse",
}
