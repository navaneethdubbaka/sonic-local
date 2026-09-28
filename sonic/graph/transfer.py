from __future__ import annotations

from typing import Any

from sonic.models.questions import ROUTE_TO_NODE

EXECUTABLE_NODES = {
    "needle_desktop",
    "needle_search",
    "needle_google",
    "browser_graph",
}


def apply_transfer_rules(
    *,
    route: str,
    risk: str,
    needs_tool: str,
    complexity: str,
    route_confidence: float,
    route_threshold: float,
) -> dict[str, Any]:
    """Map Laya answers to exactly one next node. PRD section 8.2."""
    notes: list[str] = []

    if risk == "refuse":
        return {
            "route": "refuse",
            "next_node": "refuse",
            "model_used": "none",
            "notes": ["risk=refuse"],
            "would_execute_tool": False,
        }

    if route_confidence < route_threshold and route != "clarify":
        notes.append(f"route confidence {route_confidence:.3f} < {route_threshold}")
        route = "clarify"

    if needs_tool == "prose" and route in {
        "desktop",
        "browser",
        "web_search",
        "google",
    }:
        notes.append("needs_tool=prose overrides tool route")
        route = "cloud_answer"

    if needs_tool == "tool" and route == "cloud_answer":
        # Keep cloud for prose answers; tool-intent cloud_answer becomes clarify
        # unless complexity is open_reasoning (general Q that mentions tools loosely).
        if complexity != "open_reasoning":
            notes.append("needs_tool=tool with cloud_answer -> clarify")
            route = "clarify"

    next_node = ROUTE_TO_NODE.get(route, "ask_user")
    model_used = {
        "needle_desktop": "needle",
        "needle_search": "needle",
        "needle_google": "needle",
        "browser_graph": "laya+needle",
        "cloud_chat": "cloud",
        "ask_user": "none",
        "calculator": "calculator",
        "refuse": "none",
    }.get(next_node, "none")

    return {
        "route": route,
        "next_node": next_node,
        "model_used": model_used,
        "notes": notes,
        "would_execute_tool": next_node in EXECUTABLE_NODES,
    }
