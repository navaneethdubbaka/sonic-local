from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WAKE = ROOT / "local wakeword model" / "sonic_india2.onnx"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    wake_enabled: bool = Field(default=False, alias="SONIC_WAKE_ENABLED")
    wake_model: Path = Field(default=DEFAULT_WAKE, alias="SONIC_WAKE_MODEL")
    device: Literal["auto", "cpu", "gpu"] = Field(default="auto", alias="SONIC_DEVICE")

    laya_checkpoint: Literal["typed-decisions", "english", "multilingual"] = Field(
        default="english",
        alias="SONIC_LAYA_CHECKPOINT",
    )
    laya_runtime: Literal["auto", "torch", "onnx"] = Field(
        default="auto",
        alias="SONIC_LAYA_RUNTIME",
    )
    laya_route_threshold: float = Field(default=0.35, alias="SONIC_LAYA_ROUTE_THRESHOLD")

    needle_weights: str | None = Field(default=None, alias="SONIC_NEEDLE_WEIGHTS")
    needle_act_threshold: float = Field(default=0.55, alias="SONIC_NEEDLE_ACT_THRESHOLD")

    cloud_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="SONIC_CLOUD_BASE_URL",
    )
    cloud_model: str = Field(default="gpt-4o-mini", alias="SONIC_CLOUD_MODEL")
    cloud_api_key: str | None = Field(default=None, alias="SONIC_CLOUD_API_KEY")

    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")


def get_settings() -> Settings:
    return Settings()
