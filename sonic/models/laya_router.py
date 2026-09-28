from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sonic.config import Settings
from sonic.device import DevicePlan
from sonic.models.questions import (
    COMPLEXITY_CRITERIA,
    RISK_CRITERIA,
    build_laya_state,
    routing_questions,
)

logger = logging.getLogger(__name__)

CHECKPOINT_IDS = {
    "typed-decisions": ("convaiinnovations/laya-typed-decisions", None),
    "english": ("convaiinnovations/laya", None),
    "multilingual": ("convaiinnovations/laya", "multilingual"),
}


@dataclass
class RouteDecision:
    route: str
    risk: str
    needs_tool: str
    complexity: str
    route_confidence: float
    risk_score: float
    complexity_score: float
    raw_answers: dict[str, Any]
    runtime: str
    provider: str


class LayaDecisionModel:
    """Loads typed-decisions with torch (GPU/CPU) or ONNX when configured."""

    def __init__(self, settings: Settings, plan: DevicePlan) -> None:
        self.settings = settings
        self.plan = plan
        self.runtime = "unset"
        self.provider = "unset"
        self._agent = self._load()

    def _load(self) -> Any:
        model_id, subfolder = CHECKPOINT_IDS[self.settings.laya_checkpoint]
        prefer_onnx = self.settings.laya_runtime == "onnx"
        prefer_torch = self.settings.laya_runtime == "torch"
        auto = self.settings.laya_runtime == "auto"

        if prefer_onnx or (auto and False):
            # ONNX path is optional until an exported typed-decisions graph is present.
            agent = self._try_onnx(model_id, subfolder)
            if agent is not None:
                return agent
            if prefer_onnx:
                raise RuntimeError(
                    "SONIC_LAYA_RUNTIME=onnx but no ONNX graph was found. "
                    "Export typed-decisions or set SONIC_LAYA_RUNTIME=torch."
                )

        if prefer_torch or auto or prefer_onnx:
            return self._load_torch(model_id, subfolder)

        raise RuntimeError(f"unsupported laya runtime: {self.settings.laya_runtime}")

    def _try_onnx(self, model_id: str, subfolder: str | None) -> Any | None:
        onnx_path = self.settings.wake_model.parent.parent / "onnx" / "laya.onnx"
        if not onnx_path.exists():
            logger.info("no local onnx at %s; using torch", onnx_path)
            return None
        try:
            from laya.onnx_agent import ONNXAgent

            agent = ONNXAgent(model_id, onnx_path=str(onnx_path), subfolder=subfolder)
            self.runtime = "onnx"
            self.provider = ",".join(self.plan.onnx_providers)
            logger.info("laya onnx loaded providers=%s", self.provider)
            return agent
        except Exception as exc:  # noqa: BLE001
            logger.warning("onnx laya failed: %s", exc)
            return None

    def _load_torch(self, model_id: str, subfolder: str | None) -> Any:
        import laya

        device = self.plan.torch_device
        kwargs: dict[str, Any] = {"device": device}
        if subfolder:
            kwargs["subfolder"] = subfolder
        agent = laya.load(model_id, **kwargs)
        self.runtime = "torch"
        self.provider = device
        logger.info("laya torch loaded device=%s checkpoint=%s", device, model_id)
        return agent

    def decide(
        self,
        utterance: str,
        *,
        foreground_window: str = "",
    ) -> RouteDecision:
        state = build_laya_state(utterance, foreground_window=foreground_window)
        result = self._agent.predict(state, routing_questions())
        answers = result["answers"]

        route = str(answers["route"]["choice"])
        route_conf = float(
            answers["route"].get("answer_confidence")
            or answers["route"].get("confidence")
            or 0.0
        )
        probs = answers["route"].get("probabilities")
        if isinstance(probs, dict) and route in probs:
            route_conf = max(route_conf, float(probs[route]))

        risk_score = float(answers["risk"]["score"])
        risk = _bucket_score(risk_score, len(RISK_CRITERIA) - 1, ["observe", "confirm", "refuse"])

        needs_tool = str(answers["needs_tool"]["choice"])
        complexity_score = float(answers["complexity"]["score"])
        complexity = _bucket_score(
            complexity_score,
            len(COMPLEXITY_CRITERIA) - 1,
            ["single_step", "multi_step", "open_reasoning"],
        )

        return RouteDecision(
            route=route,
            risk=risk,
            needs_tool=needs_tool,
            complexity=complexity,
            route_confidence=route_conf,
            risk_score=risk_score,
            complexity_score=complexity_score,
            raw_answers=answers,
            runtime=self.runtime,
            provider=self.provider,
        )


def _bucket_score(score: float, max_level: int, labels: list[str]) -> str:
    level = int(round(max(0.0, min(float(max_level), score))))
    return labels[level]
