"""CQP estimation, SSIM scoring, and the smart compress-to-target loop."""

import math
import subprocess
from pathlib import Path

import config
from encoder import run_encode


def estimate_start_cqp(encoder: str, src_size: int, target_size: int, default_cqp: int) -> int:
    """
    Bitrate math starting point: every +6 CQP roughly halves bitrate.
      delta = 6 * log2(src / target)
    Back off 4 steps below estimate to avoid skipping the quality sweet spot.
    """
    if target_size >= src_size:
        return default_cqp
    delta = int(6 * math.log2(src_size / target_size))
    estimated = default_cqp + delta
    cap = config.max_cqp(config.codec_family(encoder)) - 2
    return max(default_cqp, min(estimated - 4, cap))


def calc_ssim(ffmpeg: str, src: Path, compressed: Path, match_height: int | None = None) -> float | None:
    """
    Run ffmpeg's SSIM filter. When match_height is set (i.e. output was
    downscaled), scale src to the same height before comparing so the score
    reflects compression quality, not resolution difference.
    """
    if match_height:
        lavfi = f"[0:v]scale=-2:{match_height}:flags=lanczos[ref];[ref][1:v]ssim"
    else:
        lavfi = "[0:v][1:v]ssim"

    cmd = [
        ffmpeg, "-y",
        "-i", str(src),
        "-i", str(compressed),
        "-lavfi", lavfi,
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in result.stderr.splitlines():
        if "All:" in line:
            try:
                return float(line.split("All:")[1].split()[0])
            except (IndexError, ValueError):
                pass
    return None


def compress_to_target(
    ffmpeg: str,
    src: Path,
    dst: Path,
    encoder: str,
    default_cqp: int,
    size_limit: int | None,
    scale_height: int | None = None,
) -> bool:
    """
    Binary search CQP at a fixed resolution until output fits size_limit.
    Returns True if a file was written to dst.
    """
    if size_limit is None:
        res_label = f" at {scale_height}p" if scale_height else ""
        print(f"  CQP {default_cqp}{res_label}  (no size limit)\n")
        return run_encode(ffmpeg, src, dst, encoder, default_cqp, scale_height)

    lo = estimate_start_cqp(encoder, src.stat().st_size, size_limit, default_cqp)
    hi = config.max_cqp(config.codec_family(encoder))
    best: Path | None = None

    res_label = f" at {scale_height}p" if scale_height else ""
    print(f"  Target: {config.fmt_mb(size_limit)}  |  CQP {lo}-{hi}{res_label}\n")

    for attempt in range(1, 9):
        cqp = (lo + hi) // 2
        tmp = dst.parent / f"_sc_tmp_{cqp}.mp4"

        print(f"  Pass {attempt}  CQP {cqp:>2} ...", end="  ", flush=True)
        if not run_encode(ffmpeg, src, tmp, encoder, cqp, scale_height):
            return False

        size = tmp.stat().st_size
        fits = size <= size_limit
        print(f"{config.fmt_mb(size)}  {'OK fits' if fits else 'X  too big'}")

        if fits:
            if best and best.exists():
                best.unlink()
            best = tmp
            hi = cqp - 1
        else:
            tmp.unlink()
            lo = cqp + 1

        if lo > hi:
            break

    if best:
        best.rename(dst)
        return True
    return False


def compress_smart(
    ffmpeg: str,
    src: Path,
    dst: Path,
    encoder: str,
    default_cqp: int,
    size_limit: int | None,
    src_height: int,
) -> tuple[bool, float | None, int | None]:
    """
    Full smart pipeline:
      1. Try binary-search CQP at original resolution.
      2. Check SSIM — if above floor, done.
      3. If quality is poor OR size limit unreachable, drop to next resolution step.
      4. Repeat until a good result is found or all steps exhausted.

    Returns (success, ssim_score, scale_height_used).
    scale_height_used=None means original resolution was kept.
    """
    floor   = config.ssim_floor()
    steps   = config.resolution_steps()
    # Only include resolutions strictly smaller than the source
    ladder  = [None] + [h for h in steps if h < src_height]

    for res in ladder:
        label = f"{res}p" if res else f"{src_height}p (original)"
        print(f"\n--- Resolution: {label} ---\n")

        success = compress_to_target(ffmpeg, src, dst, encoder, default_cqp, size_limit, res)

        if not success:
            print(f"  Could not hit target at {label}.")
            if res != ladder[-1]:
                print("  Dropping to lower resolution...")
            continue

        # Score quality — scale src to match output height for a fair comparison
        print(f"\n  Checking quality (SSIM)...", end="  ", flush=True)
        ssim = calc_ssim(ffmpeg, src, dst, match_height=res)

        if ssim is None:
            print("unavailable — accepting result.")
            return True, None, res

        print(f"SSIM {ssim:.4f}  -  {config.ssim_label(ssim)}")

        if ssim >= floor:
            return True, ssim, res

        print(f"  Quality below floor ({floor}) — dropping to lower resolution...")
        if dst.exists():
            dst.unlink()

    return False, None, None
