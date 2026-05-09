"""Video analysis - metadata extraction and content complexity scoring."""

import json
import shutil
import subprocess
from pathlib import Path


def _ffprobe_path() -> str:
    if shutil.which("ffprobe"):
        return "ffprobe"
    raise RuntimeError(
        "ffprobe not found. Install ffmpeg (full build) and add it to PATH."
    )


def get_video_info(src: Path) -> dict:
    """
    Returns resolution, fps, bitrate, duration, and a complexity score.

    Complexity is measured as bits-per-pixel-per-frame (bppf):
      bppf = bitrate / (width * height * fps)
    Higher = more complex content (fast motion, film grain, high detail).
    """
    ffprobe = _ffprobe_path()
    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", str(src)],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)

    video = next(s for s in data["streams"] if s.get("codec_type") == "video")
    width  = int(video["width"])
    height = int(video["height"])

    num, den = video.get("r_frame_rate", "30/1").split("/")
    fps = float(num) / float(den)

    fmt      = data.get("format", {})
    bitrate  = int(fmt.get("bit_rate", 0))
    duration = float(fmt.get("duration", 0))

    bppf = bitrate / (width * height * fps) if width * height * fps > 0 else 0

    if bppf < 0.05:
        complexity       = "Simple"
        complexity_hint  = "clean content, compresses very well"
    elif bppf < 0.15:
        complexity       = "Medium"
        complexity_hint  = "typical game / screen recording"
    else:
        complexity       = "Complex"
        complexity_hint  = "high motion, grain, or fine detail — harder to compress"

    return {
        "width":          width,
        "height":         height,
        "fps":            round(fps, 2),
        "bitrate_kbps":   bitrate // 1000,
        "duration_s":     round(duration, 1),
        "bppf":           round(bppf, 4),
        "complexity":     complexity,
        "complexity_hint": complexity_hint,
    }
