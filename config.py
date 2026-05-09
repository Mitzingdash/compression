"""Loads config.json and exposes typed helpers used across the project."""

import json
from pathlib import Path

HERE = Path(__file__).parent
_cfg: dict = json.loads((HERE / "config.json").read_text())


def presets() -> list[dict]:
    return _cfg["presets"]

def encoder_candidates() -> dict[str, list[str]]:
    return _cfg["encoder_candidates"]

def default_cqp(encoder: str) -> int:
    return _cfg["default_cqp"][encoder]

def max_cqp(family: str) -> int:
    return _cfg["max_cqp"][family]

def ssim_label(score: float) -> str:
    for entry in _cfg["ssim_labels"]:
        if score >= entry["min"]:
            return entry["label"]
    return "Poor"

def codec_family(encoder: str) -> str:
    if "264" in encoder:                       return "h264"
    if "265" in encoder or "hevc" in encoder:  return "h265"
    return "av1"

def ssim_floor() -> float:
    return _cfg["ssim_floor"]

def resolution_steps() -> list[int]:
    return _cfg["resolution_steps"]

def fmt_mb(n: int) -> str:
    return f"{n / 1024 / 1024:.2f} MB"
