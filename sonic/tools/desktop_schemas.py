"""Desktop tool schemas for Needle. Phase 0: compile only, never execute."""

from __future__ import annotations

from typing import Any

DESKTOP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "open_app",
        "description": "Open an allowlisted installed application by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "App name the user said, e.g. Notepad, Chrome, Spotify",
                }
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "focus_window",
        "description": "Bring a top-level window to the foreground by title query.",
        "parameters": {
            "type": "object",
            "properties": {
                "title_query": {
                    "type": "string",
                    "description": "Substring of the window title",
                }
            },
            "required": ["title_query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "type_text",
        "description": "Type text into the focused editable control.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Exact text to type"}
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "press_keys",
        "description": "Press allowlisted keys or shortcuts such as Enter or Ctrl+S.",
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of key names",
                }
            },
            "required": ["keys"],
            "additionalProperties": False,
        },
    },
    {
        "name": "click_control",
        "description": "Click a control id from the current accessibility snapshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "control_id": {
                    "type": "string",
                    "description": "Id from the current snapshot only",
                }
            },
            "required": ["control_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "web_search",
        "description": "Run one HTTP web search and return titles and snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


def tool_schemas() -> list[dict[str, Any]]:
    return list(DESKTOP_TOOLS)
