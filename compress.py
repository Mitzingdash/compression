#!/usr/bin/env python3
"""SmartCompress - entry point."""

import sys
import imageio_ffmpeg

import analysis
import config
import encoder
import pipeline
import wizard


def main() -> None:
    print("\n" + "=" * 44)
    print("  SmartCompress")
    print("=" * 44 + "\n")

    input_path = wizard.step_input()
    in_size = input_path.stat().st_size
    print(f"\n  Got: {input_path.name}  ({config.fmt_mb(in_size)})")

    # ── video analysis ────────────────────────────────────────────────────────
    print("\n  Analyzing video...", end="  ", flush=True)
    info = analysis.get_video_info(input_path)
    print(f"{info['width']}x{info['height']}  {info['fps']}fps  {info['bitrate_kbps']} kbps")
    print(f"  Complexity:  {info['complexity']} - {info['complexity_hint']}")

    wizard.divider()
    size_limit, codec_priority, preset_label = wizard.step_preset()

    wizard.divider()
    out_name, out_folder = wizard.step_output(input_path)
    output_path = out_folder / out_name

    wizard.divider()
    print("Ready - here's what will happen:\n")
    print(f"  Input:      {input_path}")
    print(f"              {config.fmt_mb(in_size)}  |  {info['complexity']} content")
    print(f"  Preset:     {preset_label}")
    if size_limit:
        print(f"  Limit:      {config.fmt_mb(size_limit)}")
    print(f"  Output:     {output_path}")
    print()
    input("  Press Enter to compress, or Ctrl+C to cancel...")

    # ── encoder selection ─────────────────────────────────────────────────────
    print("\nProbing encoders...")
    ffmpeg   = imageio_ffmpeg.get_ffmpeg_exe()
    available = encoder.probe_encoders(ffmpeg)
    enc      = encoder.pick_encoder(ffmpeg, codec_priority, available)
    if not enc:
        print("\n[ERROR] No compatible encoder found for this preset.")
        sys.exit(1)
    print(f"  Encoder: {enc}\n")

    # ── smart compress (resolution ladder + SSIM floor) ───────────────────────
    print("Encoding...\n")
    success, ssim, scale_used = pipeline.compress_smart(
        ffmpeg, input_path, output_path,
        enc, config.default_cqp(enc), size_limit,
        src_height=info["height"],
    )

    # ── H.265 fallback for H.264-only paths ───────────────────────────────────
    if not success and size_limit and codec_priority == ["h264"]:
        print()
        print("  H.264 could not reach the target at any resolution.")
        print("  H.265 compresses better but may not play inline on Discord.")
        print()
        if input("  Switch to H.265? [y/N]: ").strip().lower() == "y":
            enc = encoder.pick_encoder(ffmpeg, ["h265"], available)
            if enc:
                print(f"\n  Encoder: {enc}\n")
                print("Encoding...\n")
                success, ssim, scale_used = pipeline.compress_smart(
                    ffmpeg, input_path, output_path,
                    enc, config.default_cqp(enc), size_limit,
                    src_height=info["height"],
                )
            else:
                print("  [!] No H.265 encoder available.")

    if not success:
        if size_limit:
            print(f"\n  Could not reach {config.fmt_mb(size_limit)} with acceptable quality.")
            print("  Try a higher preset tier or use Custom with a bigger limit.")
        sys.exit(1)

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
    print("=" * 44 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
        sys.exit(0)
