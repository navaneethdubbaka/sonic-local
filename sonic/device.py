from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

DeviceMode = Literal["auto", "cpu", "gpu"]
TorchDevice = Literal["cpu", "cuda", "mps"]


@dataclass(frozen=True)
class DevicePlan:
    """Resolved compute plan for this process."""

    mode: DeviceMode
    torch_device: TorchDevice
    onnx_providers: tuple[str, ...]
    gpu_available: bool
    notes: tuple[str, ...] = ()

    def log(self) -> None:
        logger.info(
            "device plan mode=%s torch=%s onnx=%s gpu=%s%s",
            self.mode,
            self.torch_device,
            ",".join(self.onnx_providers),
            self.gpu_available,
            f" notes={';'.join(self.notes)}" if self.notes else "",
        )


def _onnx_available() -> list[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers())
    except Exception as exc:  # noqa: BLE001
        logger.warning("onnxruntime unavailable: %s", exc)
        return []


def _cuda_usable() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def probe_device(mode: DeviceMode = "auto") -> DevicePlan:
    """Pick GPU when present, otherwise CPU. `gpu` mode raises if nothing loads."""
    available = _onnx_available()
    notes: list[str] = []
    providers: list[str] = []
    torch_device: TorchDevice = "cpu"
    gpu = False

    has_cuda_ort = "CUDAExecutionProvider" in available
    has_dml = "DmlExecutionProvider" in available
    has_torch_cuda = _cuda_usable()

    if mode == "cpu":
        providers = ["CPUExecutionProvider"]
        notes.append("forced cpu")
    else:
        if has_torch_cuda:
            torch_device = "cuda"
            gpu = True
        if has_cuda_ort:
            providers.append("CUDAExecutionProvider")
            gpu = True
        elif has_dml:
            providers.append("DmlExecutionProvider")
            gpu = True
            notes.append("onnx via DirectML")
        else:
            notes.append("no onnx gpu provider")

        providers.append("CPUExecutionProvider")

        if mode == "gpu" and not gpu:
            raise RuntimeError(
                "SONIC_DEVICE=gpu but neither CUDA nor DirectML is available"
            )

    # Deduplicate while keeping order
    seen: set[str] = set()
    ordered: list[str] = []
    for p in providers:
        if p not in seen:
            seen.add(p)
            ordered.append(p)

    plan = DevicePlan(
        mode=mode,
        torch_device=torch_device,
        onnx_providers=tuple(ordered),
        gpu_available=gpu,
        notes=tuple(notes),
    )
    plan.log()
    return plan
