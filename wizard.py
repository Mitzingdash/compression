"""Interactive wizard steps — collects input file, preset, and output location."""

from pathlib import Path

import config

HERE = Path(__file__).parent


def ask(prompt: str, default: str = "") -> str:
    hint = f" (default: {default})" if default else ""
    val = input(f"  {prompt}{hint}:\n  > ").strip().strip('"').strip("'")
    return val if val else default


def divider():
    print("\n" + "─" * 44 + "\n")


def step_input() -> Path:
    print("STEP 1 — Input file")
    print("  Drag & drop a file into this window, or paste the full path.\n")
    while True:
        raw = input("  > ").strip().strip('"').strip("'")
        path = Path(raw)
        if path.exists() and path.is_file():
            return path
        print(f"\n  [!] Can't find that file — try again.\n")


def step_preset() -> tuple[int | None, list[str], str]:
    """Returns (size_limit_bytes or None, codec_priority, label)."""
    print("STEP 2 — Target preset")
    print("  What are you compressing for?\n")

    preset_list = config.presets()
    for p in preset_list:
        print(f"  [{p['key']}]  {p['label']}")
    print()

    preset_map = {p["key"]: p for p in preset_list}
    while True:
        choice = input("  > ").strip()
        if choice in preset_map:
            p = preset_map[choice]
            break
        print(f"  [!] Enter a number 1–{len(preset_list)}.\n")

    size_limit     = int(p["size_mb"] * 1024 * 1024) if p["size_mb"] else None
    codec_priority = list(p["codecs"])
    label          = p["label"]

    # Discord presets are h264-only for inline playback — offer H.265 opt-in
    if codec_priority == ["h264"]:
        print()
        print("  Discord presets use H.264 for inline playback.")
        print("  H.265 compresses better but some Discord users will get a")
        print("  download prompt instead of watching inline.")
        print()
        if input("  Use H.265 instead? [y/N]: ").strip().lower() == "y":
            codec_priority = ["h265"]
            label += "  (H.265)"
        print()

    if p["id"] == "custom":
        print()
        while True:
            raw = input("  Custom size limit in MB (or leave blank for none):\n  > ").strip()
            if not raw:
                size_limit = None
                break
            try:
                size_limit = int(float(raw) * 1024 * 1024)
                label = f"Custom ({raw} MB)"
                break
            except ValueError:
                print("  [!] Enter a number like 50\n")

    return size_limit, codec_priority, label


def step_output(input_path: Path) -> tuple[str, Path]:
    """Returns (filename, output_folder)."""
    print("STEP 3 — Output filename")
    default_name = f"{input_path.stem}_compressed.mp4"
    out_name = ask("Filename", default_name)
    if not out_name.lower().endswith(".mp4"):
        out_name += ".mp4"

    divider()

    print("STEP 4 — Output folder")
    default_folder = str(HERE / "out")
    raw_folder = ask("Folder", default_folder)
    out_folder = Path(raw_folder.strip('"').strip("'"))
    out_folder.mkdir(parents=True, exist_ok=True)

    return out_name, out_folder
