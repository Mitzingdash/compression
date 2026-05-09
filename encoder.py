"""Encoder probing, validation, selection, and raw ffmpeg encoding."""

import subprocess
from pathlib import Path

import config


def probe_encoders(ffmpeg: str) -> set[str]:
    """Return all video encoder names compiled into this ffmpeg build."""
    result = subprocess.run(
        [ffmpeg, "-encoders", "-v", "quiet"],
        capture_output=True, text=True,
    )
    found = set()
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and len(parts[0]) >= 6 and parts[0][0] == "V":
            found.add(parts[1])
    return found


def test_encoder(ffmpeg: str, encoder: str) -> bool:
    """Encode a tiny dummy clip to catch CUDA/AMF runtime failures.
    AMF requires yuv420p and a minimum resolution to initialize."""
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "color=black:size=256x144:rate=30:duration=0.5",
        "-pix_fmt", "yuv420p",
        "-c:v", encoder,
        "-f", "null", "-",
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def pick_encoder(ffmpeg: str, codec_priority: list[str], available: set[str]) -> str | None:
    """Walk the priority list and return the first encoder that actually works."""
    candidates = config.encoder_candidates()
    for family in codec_priority:
        for encoder in candidates[family]:
            if encoder in available:
                if test_encoder(ffmpeg, encoder):
                    return encoder
                print(f"  {encoder} — registered but not usable, skipping...")
    return None


def run_encode(
    ffmpeg: str, src: Path, dst: Path, encoder: str, cqp: int,
    scale_height: int | None = None,
) -> bool:
    """Run a single ffmpeg encode. Pass scale_height to downscale video."""
    if "nvenc" in encoder:
        quality = ["-rc", "vbr", "-cq", str(cqp), "-b:v", "0"]
    elif "amf" in encoder:
        quality = ["-rc", "cqp", "-qp_i", str(cqp), "-qp_p", str(cqp), "-qp_b", str(cqp)]
    else:
        quality = ["-crf", str(cqp)]

    scale = ["-vf", f"scale=-2:{scale_height}:flags=lanczos"] if scale_height else []

    cmd = [
        ffmpeg, "-y",
        "-i", str(src),
        "-c:v", encoder, *quality,
        *scale,
        "-c:a", "aac", "-b:a", "128k",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n[ERROR] ffmpeg failed:\n{result.stderr[-3000:]}")
        return False
    return True
