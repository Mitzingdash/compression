"""CQP binary search, SSIM scoring, and the smart compress pipeline."""

import math
import subprocess
import threading
from pathlib import Path

import config
import log
from encoder import run_encode, progress_bar


def calc_ssim(
    ffmpeg: str, src: Path, compressed: Path,
    match_height: int | None = None,
    duration_s: float = 0.0,
) -> float | None:
    """
    Run ffmpeg's SSIM filter with a live progress bar.
    When match_height is set, scale src to the same height first so the score
    reflects compression quality, not resolution difference.
    """
    if match_height:
        lavfi = f"[0:v]scale=-2:{match_height}:flags=lanczos[ref];[ref][1:v]ssim"
    else:
        lavfi = "[0:v][1:v]ssim"

    cmd = [
        ffmpeg, "-y",
        "-progress", "pipe:1", "-nostats",
        "-i", str(src),
        "-i", str(compressed),
        "-lavfi", lavfi,
        "-f", "null", "-",
    ]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace",
    )

    ssim_val: list[float] = []
    stderr_lines: list[str] = []

    def _drain() -> None:
        for line in proc.stderr:
            stderr_lines.append(line)
            if "All:" in line:
                try:
                    ssim_val.append(float(line.split("All:")[1].split()[0]))
                except (IndexError, ValueError):
                    pass

    t = threading.Thread(target=_drain, daemon=True)
    t.start()

    shown_bar = False
    for line in proc.stdout:
        key, _, val = line.strip().partition("=")
        if key == "out_time_us" and duration_s > 0:
            try:
                us = int(val)
                if us >= 0:
                    pct = min(us / (duration_s * 1_000_000), 1.0)
                    print(f"\r    Quality   {progress_bar(pct)}", end="", flush=True)
                    shown_bar = True
            except ValueError:
                pass

    proc.wait()
    t.join()

    if shown_bar:
        print(f"\r    Quality   {progress_bar(1.0)}", flush=True)

    return ssim_val[0] if ssim_val else None


def compress_to_target(
    ffmpeg: str,
    src: Path,
    dst: Path,
    encoder: str,
    default_cqp: int,
    size_limit: int | None,
    scale_height: int | None = None,
    src_bitrate_kbps: int = 0,
    duration_s: float = 0.0,
    complexity: str = "Medium",
) -> bool:
    """
    Binary search CQP from default_cqp upward until the smallest file that
    still fits size_limit is found. Returns True if a file was written to dst.
    """
    if size_limit is None:
        res_label = f" at {scale_height}p" if scale_height else ""
        msg = f"  CQP {default_cqp}{res_label}  (no size limit)"
        print(msg)
        log.w(msg)
        print()
        return run_encode(ffmpeg, src, dst, encoder, default_cqp, scale_height, duration_s)

    lo = default_cqp
    hi = config.max_cqp(encoder, complexity)
    best: Path | None = None

    res_label = f" at {scale_height}p" if scale_height else ""
    header = f"  Target: {config.fmt_mb(size_limit)}  |  CQP {lo}-{hi}{res_label}"
    print(header)
    log.w(header)
    print()

    for attempt in range(1, 9):
        cqp = (lo + hi) // 2
        tmp = dst.parent / f"_sc_tmp_{cqp}.mp4"

        pass_line = f"  Pass {attempt}  CQP {cqp:>2}"
        print(pass_line)
        log.w(pass_line)

        if not run_encode(ffmpeg, src, tmp, encoder, cqp, scale_height, duration_s):
            return False

        size = tmp.stat().st_size
        fits = size <= size_limit
        result_line = f"    {config.fmt_mb(size)}  {'OK fits' if fits else 'X  too big'}"
        print(result_line)
        log.w(result_line)

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
        best.replace(dst)
        return True
    return False


def compress_no_limit(
    ffmpeg: str,
    src: Path,
    dst: Path,
    encoder: str,
    default_cqp: int,
    ssim_floor: float,
    scale_height: int | None = None,
    duration_s: float = 0.0,
) -> tuple[bool, float | None]:
    """
    No size limit mode — binary search for the HIGHEST CQP where SSIM
    stays above the floor. Gives the smallest file that still looks good.
    Returns (success, final_ssim).
    """
    max_q  = config.max_cqp(encoder)
    lo, hi = default_cqp, max_q
    best: tuple[int, Path, float] | None = None   # (cqp, tmp_path, ssim)

    header = f"  Squeezing: SSIM floor {ssim_floor}  |  CQP {lo}-{hi}"
    print(header)
    log.w(header)
    print()

    for attempt in range(1, 9):
        cqp = (lo + hi) // 2
        tmp = dst.parent / f"_sc_tmp_{cqp}.mp4"

        pass_line = f"  Pass {attempt}  CQP {cqp:>2}"
        print(pass_line)
        log.w(pass_line)

        if not run_encode(ffmpeg, src, tmp, encoder, cqp, scale_height, duration_s):
            return False, None

        size = tmp.stat().st_size
        ssim = calc_ssim(ffmpeg, src, tmp, match_height=scale_height, duration_s=duration_s)

        if ssim is None:
            msg = f"    {config.fmt_mb(size)}  SSIM unavailable - accepting"
            print(msg)
            log.w(msg)
            if best:
                best[1].unlink(missing_ok=True)
            tmp.replace(dst)
            return True, None

        fits = ssim >= ssim_floor
        result_line = f"    {config.fmt_mb(size)}  SSIM {ssim:.4f}  {'OK' if fits else 'X quality too low'}"
        print(result_line)
        log.w(result_line)

        if fits:
            if best:
                best[1].unlink(missing_ok=True)
            best = (cqp, tmp, ssim)
            lo = cqp + 1        # still above floor — can we push harder?
        else:
            tmp.unlink(missing_ok=True)
            hi = cqp - 1        # went too far, back off

        if lo > hi:
            break

    if best:
        best[1].replace(dst)
        return True, best[2]   # reuse already-computed SSIM, no second check

    # Couldn't even pass the floor at default_cqp — just encode at default
    msg = "  Could not improve on default quality — encoding at default CQP."
    print(msg)
    log.w(msg)
    ok = run_encode(ffmpeg, src, dst, encoder, default_cqp, scale_height, duration_s)
    return ok, None


def compress_smart(
    ffmpeg: str,
    src: Path,
    dst: Path,
    encoder: str,
    default_cqp: int,
    size_limit: int | None,
    src_height: int,
    info: dict,
    forced_res: int = 0,
) -> tuple[bool, float | None, int | None]:
    """
    Full smart pipeline. forced_res=0 means auto (full resolution ladder).
    Any other value forces a specific output height.

    Returns (success, ssim_score, scale_height_used).
    scale_height_used=None means original resolution was kept.
    """
    complexity  = info.get("complexity", "Medium")
    floor       = config.ssim_floor(complexity)
    steps       = config.resolution_steps()
    duration_s  = info.get("duration_s", 0.0)
    min_height  = config.min_output_height(src_height)

    # Build resolution ladder
    if forced_res == 0:
        ladder = [None] + [h for h in steps if h < src_height and h >= min_height]
    else:
        scale  = None if forced_res >= src_height else forced_res
        ladder = [scale]

    floor_line = f"  Quality floor:  SSIM {floor}  ({complexity} content)"
    print(floor_line)
    log.w(floor_line)
    if size_limit and forced_res == 0:
        cap_line = f"  Resolution cap: {min_height}p minimum  (source: {src_height}p)"
        print(cap_line)
        log.w(cap_line)
    print()

    # ── no size limit: squeeze at chosen resolution ───────────────────────────
    if size_limit is None:
        scale = ladder[0]
        label = f"{src_height}p (original)" if scale is None else f"{scale}p"
        res_header = f"\n--- Resolution: {label} ---"
        print(res_header)
        log.w(res_header)
        print()
        success, ssim = compress_no_limit(
            ffmpeg, src, dst, encoder, default_cqp, floor,
            scale_height=scale, duration_s=duration_s,
        )
        return success, ssim, scale

    # ── size-limited: try resolution(s) in order ─────────────────────────────
    for res in ladder:
        label = f"{res}p" if res else f"{src_height}p (original)"
        res_header = f"\n--- Resolution: {label} ---"
        print(res_header)
        log.w(res_header)
        print()

        success = compress_to_target(
            ffmpeg, src, dst, encoder, default_cqp, size_limit, res,
            src_bitrate_kbps=info.get("bitrate_kbps", 0),
            duration_s=duration_s,
            complexity=complexity,
        )

        if not success:
            if len(ladder) == 1:
                msg = f"  Could not hit target at {label}."
                print(msg)
                log.w(msg)
                print("  Try a lower resolution or a larger size limit.")
            elif res == ladder[-1]:
                msg = f"  Could not hit target at {label} (minimum resolution reached)."
                print(msg)
                log.w(msg)
            else:
                msg = f"  Could not hit target at {label} - dropping to lower resolution..."
                print(msg)
                log.w(msg)
            continue

        print()
        ssim = calc_ssim(ffmpeg, src, dst, match_height=res, duration_s=duration_s)

        if ssim is None:
            msg = "  SSIM unavailable - accepting result."
            print(msg)
            log.w(msg)
            return True, None, res

        ssim_line = f"  SSIM {ssim:.4f}  -  {config.ssim_label(ssim)}  (floor: {floor}  [{complexity}])"
        print(ssim_line)
        log.w(ssim_line)

        if ssim >= floor:
            return True, ssim, res

        # Quality missed the floor
        if len(ladder) == 1:
            msg = f"  Quality below {complexity} floor - but resolution was manually set, keeping result."
            print(msg)
            log.w(msg)
            return True, ssim, res

        msg = f"  Quality below {complexity} floor ({floor}) - dropping to lower resolution..."
        print(msg)
        log.w(msg)
        if dst.exists():
            dst.unlink()

    return False, None, None
