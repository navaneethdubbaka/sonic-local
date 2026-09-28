from __future__ import annotations

import logging
from typing import Any

from sonic.config import Settings

logger = logging.getLogger(__name__)


class CloudChat:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.cloud_api_key)

    def answer(self, utterance: str) -> dict[str, Any]:
        if not self.configured:
            return {
                "ok": False,
                "text": None,
                "error": "SONIC_CLOUD_API_KEY not set",
                "called": False,
            }
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = ChatOpenAI(
                model=self.settings.cloud_model,
                api_key=self.settings.cloud_api_key,
                base_url=self.settings.cloud_base_url,
                temperature=0,
            )
            msg = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are Sonic, a concise PC assistant. "
                            "Answer in one or two short sentences. Do not call tools."
                        )
                    ),
                    HumanMessage(content=utterance),
                ]
            )
            return {"ok": True, "text": str(msg.content), "error": None, "called": True}
        except Exception as exc:  # noqa: BLE001
            logger.exception("cloud chat failed")
            return {"ok": False, "text": None, "error": str(exc), "called": True}
