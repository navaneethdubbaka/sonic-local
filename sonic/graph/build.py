from __future__ import annotations

import logging
from typing import Any

from sonic.calculator import try_calculator
from sonic.config import Settings
from sonic.device import DevicePlan
from sonic.graph.transfer import apply_transfer_rules
from sonic.models.cloud import CloudChat
from sonic.models.laya_router import LayaDecisionModel
from sonic.models.needle_tools import NeedleDesktopDryRun
from sonic.safety import is_hard_refuse

logger = logging.getLogger(__name__)


class Phase0Runtime:
    """Shared models for the Phase 0 LangGraph."""

    def __init__(self, settings: Settings, plan: DevicePlan) -> None:
        self.settings = settings
        self.plan = plan
        self._laya: LayaDecisionModel | None = None
        self._needle: NeedleDesktopDryRun | None = None
        self.cloud = CloudChat(settings)

    @property
    def laya(self) -> LayaDecisionModel:
        if self._laya is None:
            self._laya = LayaDecisionModel(self.settings, self.plan)
        return self._laya

    @property
    def needle(self) -> NeedleDesktopDryRun:
        if self._needle is None:
            self._needle = NeedleDesktopDryRun(self.settings)
        return self._needle

    def run_turn(
        self,
        utterance: str,
        *,
        foreground_window: str = "",
        allow_cloud: bool = True,
        needle_dry_run: bool = True,
    ) -> dict[str, Any]:
        calc = try_calculator(utterance)
        if calc:
            return {
                "utterance": utterance,
                "route": "calculator",
                "risk": "observe",
                "needs_tool": "prose",
                "complexity": "single_step",
                "route_confidence": 1.0,
                "next_node": "calculator",
                "model_used": "calculator",
                "tool_calls": [],
                "confidence": 1.0,
                "result_text": calc["text"],
                "error": None,
                "cloud_called": False,
                "would_execute_tool": False,
                "laya_runtime": self._laya.runtime if self._laya else "not_loaded",
                "laya_provider": self._laya.provider if self._laya else "not_loaded",
                "notes": ["calculator intercept"],
            }

        if is_hard_refuse(utterance):
            return {
                "utterance": utterance,
                "route": "refuse",
                "risk": "refuse",
                "needs_tool": "tool",
                "complexity": "single_step",
                "route_confidence": 1.0,
                "next_node": "refuse",
                "model_used": "none",
                "tool_calls": [],
                "confidence": 1.0,
                "result_text": "I won't do that.",
                "error": None,
                "cloud_called": False,
                "would_execute_tool": False,
                "laya_runtime": self._laya.runtime if self._laya else "not_loaded",
                "laya_provider": self._laya.provider if self._laya else "not_loaded",
                "notes": ["hard refuse gate"],
            }

        decision = self.laya.decide(utterance, foreground_window=foreground_window)
        transfer = apply_transfer_rules(
            route=decision.route,
            risk=decision.risk,
            needs_tool=decision.needs_tool,
            complexity=decision.complexity,
            route_confidence=decision.route_confidence,
            route_threshold=self.settings.laya_route_threshold,
        )

        out: dict[str, Any] = {
            "utterance": utterance,
            "route": transfer["route"],
            "raw_route": decision.route,
            "risk": decision.risk,
            "needs_tool": decision.needs_tool,
            "complexity": decision.complexity,
            "route_confidence": decision.route_confidence,
            "risk_score": decision.risk_score,
            "complexity_score": decision.complexity_score,
            "next_node": transfer["next_node"],
            "model_used": transfer["model_used"],
            "tool_calls": [],
            "confidence": decision.route_confidence,
            "result_text": "",
            "error": None,
            "cloud_called": False,
            "would_execute_tool": transfer["would_execute_tool"],
            "laya_runtime": decision.runtime,
            "laya_provider": decision.provider,
            "notes": list(transfer["notes"]),
            "raw_answers": decision.raw_answers,
        }

        if transfer["next_node"] == "refuse":
            out["result_text"] = "I won't do that."
            out["model_used"] = "none"
            return out

        if transfer["next_node"] == "ask_user":
            out["result_text"] = "I need a bit more detail. Can you rephrase?"
            return out

        if transfer["next_node"] == "cloud_chat":
            if not allow_cloud:
                out["result_text"] = "(cloud skipped)"
                out["notes"].append("cloud skipped by caller")
                return out
            cloud = self.cloud.answer(utterance)
            out["cloud_called"] = bool(cloud.get("called"))
            out["result_text"] = cloud.get("text") or ""
            out["error"] = cloud.get("error")
            out["model_used"] = "cloud" if cloud.get("called") else "none"
            return out

        # Tool routes: Needle dry-run only in Phase 0
        if needle_dry_run and transfer["next_node"] in {
            "needle_desktop",
            "needle_search",
        }:
            dry = self.needle.complete(utterance)
            out["tool_calls"] = dry.function_calls
            out["confidence"] = dry.confidence if dry.confidence is not None else out["confidence"]
            if dry.error and dry.available:
                out["error"] = dry.error
                out["notes"].append("needle dry-run error")
            elif not dry.available:
                out["notes"].append(dry.error or "needle schemas only; engine not loaded")
                out["result_text"] = (
                    f"Would route to {transfer['next_node']} (needle not installed)"
                )
            else:
                out["result_text"] = (
                    f"dry-run calls={dry.function_calls!r} confidence={dry.confidence}"
                )
            # Phase 0 never executes
            out["would_execute_tool"] = False
            out["notes"].append("phase0 dry-run: tools not executed")
            return out

        out["result_text"] = f"Would run node {transfer['next_node']} (stub)"
        out["notes"].append("phase0 stub node")
        out["would_execute_tool"] = False
        return out


def build_graph(runtime: Phase0Runtime):
    """LangGraph: calculator → laya route → one terminal node."""
    from langgraph.graph import END, StateGraph

    from sonic.graph.state import TurnState

    def calculator_node(state: TurnState) -> dict[str, Any]:
        calc = try_calculator(state["utterance"])
        if not calc:
            return {}
        return {
            "route": "calculator",
            "risk": "observe",
            "needs_tool": "prose",
            "complexity": "single_step",
            "route_confidence": 1.0,
            "next_node": "calculator",
            "model_used": "calculator",
            "result_text": calc["text"],
            "cloud_called": False,
            "error": None,
        }

    def route_node(state: TurnState) -> dict[str, Any]:
        if state.get("route") == "calculator":
            return {}
        result = runtime.run_turn(
            state["utterance"],
            foreground_window=state.get("foreground_window") or "",
            allow_cloud=True,
            needle_dry_run=True,
        )
        return result

    graph = StateGraph(TurnState)
    graph.add_node("calculator", calculator_node)
    graph.add_node("route", route_node)
    graph.set_entry_point("calculator")

    def after_calculator(state: TurnState) -> str:
        if state.get("route") == "calculator":
            return END
        return "route"

    graph.add_conditional_edges("calculator", after_calculator, {END: END, "route": "route"})
    graph.add_edge("route", END)
    return graph.compile()
