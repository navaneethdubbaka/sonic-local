from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from sonic.config import Settings
from sonic.tools.desktop_schemas import DESKTOP_TOOLS, tool_schemas

logger = logging.getLogger(__name__)


@dataclass
class NeedleDryRunResult:
    available: bool
    function_calls: list[dict[str, Any]]
    confidence: float | None
    reasoning: str | None
    error: str | None = None


class NeedleDesktopDryRun:
    """Compile desktop tool schemas and optionally call Needle without executing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.schemas = tool_schemas()
        self._agent: Any | None = None
        self._available = False
        self._init_error: str | None = None
        self._try_init()

    def _try_init(self) -> None:
        try:
            import needle
        except ImportError as exc:
            self._init_error = (
                f"cactus-needle not installed ({exc}); schemas only. "
                "pip install 'sonic-local[needle]'"
            )
            logger.warning(self._init_error)
            return

        stubs = [_make_stub(spec) for spec in DESKTOP_TOOLS]
        try:
            kwargs: dict[str, Any] = {
                "tools": stubs,
                "system": "Windows desktop assistant. Dry run only. Do not invent tools.",
            }
            if self.settings.needle_weights:
                kwargs["weights"] = self.settings.needle_weights
            self._agent = needle.Needle(**kwargs)
            self._available = True
            logger.info("needle desktop dry-run ready tools=%s", [t["name"] for t in self.schemas])
        except Exception as exc:  # noqa: BLE001
            self._init_error = str(exc)
            logger.warning("needle init failed: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    def complete(self, utterance: str) -> NeedleDryRunResult:
        if not self._agent:
            return NeedleDryRunResult(
                available=False,
                function_calls=[],
                confidence=None,
                reasoning=None,
                error=self._init_error or "needle unavailable",
            )
        try:
            response = self._agent.complete(utterance)
            calls = list(response.get("function_calls") or [])
            return NeedleDryRunResult(
                available=True,
                function_calls=calls,
                confidence=response.get("confidence"),
                reasoning=response.get("reasoning"),
            )
        except Exception as exc:  # noqa: BLE001
            return NeedleDryRunResult(
                available=True,
                function_calls=[],
                confidence=None,
                reasoning=None,
                error=str(exc),
            )


def _make_stub(spec: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    """Build a stub function Needle can schema-compile but we never execute in Phase 0."""
    import needle

    name = spec["name"]
    description = spec["description"]
    params = spec["parameters"]

    def impl(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(f"Phase 0 dry-run: refusing to execute {name}")

    impl.__name__ = name
    impl.__doc__ = description
    # Annotate for schema builders that inspect signatures
    annotations: dict[str, Any] = {}
    for key, prop in params.get("properties", {}).items():
        annotations[key] = str
        if prop.get("type") == "array":
            annotations[key] = list
    required = set(params.get("required") or [])
    # defaults for optional args
    for key in list(annotations):
        if key not in required:
            pass
    impl.__annotations__ = {**annotations, "return": dict}

    return needle.tool(impl)
