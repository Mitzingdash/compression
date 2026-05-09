#!/usr/bin/env python3
"""SmartCompress - entry point."""

import os
import sys
from pathlib import Path

import imageio_ffmpeg

import analysis
import config
import encoder
import log
import pipeline
import wizard

HERE = Path(__file__).parent


def _log_dir() -> Path:
    sc_out = os.environ.get("SC_OUT_DIR")
    return Path(sc_out) / "out" if sc_out else HERE / "out"


def _compress_once() -> bool:
    """Run one compression session. Returns True if output was produced."""
    log.init(_log_dir())

    input_path = wizard.step_input()
    in_size = input_path.stat().st_size
    print(f"\n  Got: {input_path.name}  ({config.fmt_mb(in_size)})")

    # Analyse silently here — displayed in the confirmation screen below
    info = analysis.get_video_info(input_path)
    log.w(f"Input:      {input_path}")
    log.w(f"            {config.fmt_mb(in_size)}  |  {info['width']}x{info['height']}  {info['fps']}fps")
    log.w(f"Complexity: {info['complexity']}")

    wizard.divider()
    size_limit, codec_priority, preset_label = wizard.step_preset()

    wizard.divider()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    print("Probing encoders...\n")
    working = encoder.probe_working_encoders(ffmpeg)
    if not working:
        print("\n[ERROR] No working encoder found on this system.")
        log.w("[ERROR] No working encoder found.")
        log.close()
        return False
    recommended = encoder.pick_recommended(working, codec_priority)

    wizard.divider()
    enc = wizard.step_encoder(working, recommended)
    if not enc:
        print("\n[ERROR] No encoder selected.")
        log.w("[ERROR] No encoder selected.")
        log.close()
        return False

    wizard.divider()
    forced_res = wizard.step_resolution(info["height"], info["complexity"], config.resolution_steps())

    wizard.divider()
    out_name, out_folder = wizard.step_output(input_path)
    output_path = out_folder / out_name

    wizard.divider()
    print("Ready - here's what will happen:\n")
    print(f"  Input:       {input_path.name}")
    print(f"               {config.fmt_mb(in_size)}  |  {info['width']}x{info['height']}  {info['fps']}fps")
    print(f"  Complexity:  {info['complexity']} - {info['complexity_hint']}")
    print(f"  Preset:      {preset_label}")
    if size_limit:
        print(f"  Limit:       {config.fmt_mb(size_limit)}")
    print(f"  Encoder:     {enc}")
    if forced_res == 0:
        print(f"  Resolution:  Auto")
    elif forced_res >= info["height"]:
        print(f"  Resolution:  {info['height']}p (original)")
    else:
        print(f"  Resolution:  {forced_res}p (forced)")
    print(f"  Output:      {output_path}")

    log.w(f"Preset:     {preset_label}")
    if size_limit:
        log.w(f"Limit:      {config.fmt_mb(size_limit)}")
    log.w(f"Encoder:    {enc}")
    res_str = "Auto" if forced_res == 0 else (f"{info['height']}p (original)" if forced_res >= info["height"] else f"{forced_res}p (forced)")
    log.w(f"Resolution: {res_str}")
    log.w(f"Output:     {output_path}")
    log.w("")

    print()
    input("  Press Enter to compress, or Ctrl+C to cancel...")
    print()

    # ── smart compress (resolution ladder + SSIM floor) ───────────────────────
    print("Encoding...\n")
    success, ssim, scale_used = pipeline.compress_smart(
        ffmpeg, input_path, output_path,
        enc, config.default_cqp(enc), size_limit,
        src_height=info["height"], info=info, forced_res=forced_res,
    )

    # ── H.265 fallback when H.264 can't hit the target ───────────────────────
    if not success and size_limit and config.codec_family(enc) == "h264":
        h265_enc = next((e["name"] for e in working if e["family"] == "h265"), None)
        if h265_enc:
            print()
            print("  H.264 could not reach the target at any resolution.")
            print("  H.265 compresses better but may not play inline on Discord.")
            print()
            if input("  Switch to H.265? [y/N]: ").strip().lower() == "y":
                enc = h265_enc
                log.w(f"Switched to H.265 fallback: {enc}")
                print(f"\n  Encoder: {enc}\n")
                print("Encoding...\n")
                success, ssim, scale_used = pipeline.compress_smart(
                    ffmpeg, input_path, output_path,
                    enc, config.default_cqp(enc), size_limit,
                    src_height=info["height"], info=info, forced_res=forced_res,
                )

    if not success:
        if size_limit:
            msg = f"  Could not reach {config.fmt_mb(size_limit)} with acceptable quality."
            print(f"\n{msg}")
            log.w(msg)
            print("  Try a higher preset tier or use Custom with a bigger limit.")
        log.close()
        return False

    # ── result ────────────────────────────────────────────────────────────────
    out_size  = output_path.stat().st_size
    reduction = (1 - out_size / in_size) * 100
    res_label = f"{scale_used}p" if scale_used else f"{info['height']}p (original)"

    print("\n" + "=" * 44)
    print("  Done!\n")
    print(f"  Encoder:      {enc}")
    print(f"  Resolution:   {res_label}")
    print(f"  Input size:   {config.fmt_mb(in_size)}")
    print(f"  Output size:  {config.fmt_mb(out_size)}  ({reduction:.1f}% smaller)")
    if size_limit:
        status = "FITS" if out_size <= size_limit else "OVER LIMIT"
        print(f"  Limit check:  {config.fmt_mb(size_limit)}  ->  {status}")
    if ssim is not None:
        print(f"  Quality:      SSIM {ssim:.4f}  -  {config.ssim_label(ssim)}")
    else:
        print("  Quality:      SSIM unavailable")
    print(f"\n  Saved to:\n  {output_path}")
    print("=" * 44)

    log.w("")
    log.w(f"Result:     DONE")
    log.w(f"Encoder:    {enc}  |  Resolution: {res_label}")
    log.w(f"Input:      {config.fmt_mb(in_size)}")
    log.w(f"Output:     {config.fmt_mb(out_size)}  ({reduction:.1f}% smaller)")
    if size_limit:
        log.w(f"Limit:      {config.fmt_mb(size_limit)}  ->  {'FITS' if out_size <= size_limit else 'OVER LIMIT'}")
    if ssim is not None:
        log.w(f"Quality:    SSIM {ssim:.4f}  -  {config.ssim_label(ssim)}")
    log.w(f"Saved to:   {output_path}")

    log.close()
    return True


def main() -> None:
    print("\n" + "=" * 44)
    print(f"  SmartCompress  v{config.version()}")
    print("=" * 44 + "\n")

    while True:
        _compress_once()
        print()
        again = input("  Compress another file? [y/N]: ").strip().lower()
        if again != "y":
            break
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.close()
        print("\n\n  Cancelled.")
        sys.exit(0)
