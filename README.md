# SmartCompress

> Drag in a video (or a folder full of them), pick a target, get smaller files. No uploads, no manual settings, no potato quality.

A fast, local video compressor that figures out the encoder, resolution and quality settings for you. Built around a learning predictor so each run gets faster as it learns your hardware's behaviour.

**Status:** v3.1.0 — Windows, Linux, and macOS (Intel + Apple Silicon).

---

## What's new in v3.1.0

- **Linux and macOS builds** — self-contained binaries for `linux-x64`, `osx-x64`, `osx-arm64` alongside Windows
- **VideoToolbox** — macOS hardware encoding via `h264_videotoolbox` / `hevc_videotoolbox`
- **System ffmpeg auto-detection** — if `ffmpeg` and `ffprobe` are already on your `PATH`, SmartCompress uses them and skips the 75 MB download (great on Linux where ffmpeg is usually installed)

> Linux AMD users currently fall back to CPU encoders (libx264/libx265/libsvtav1). Full VAAPI hardware support is the focus for 3.2.0.

## What's in v3.0.0

- **Full rewrite in C#** — single self-contained binary, no Python, no virtualenv, no pip
- **Batch mode** — drop a folder, get a per-file preview table, then run the whole thing
- **Benchmark mode** — sweeps your GPU encoders across CQPs and resolutions to populate a high-quality reference cache
- **Two-path Estimator** — predicts up-front whether your size limit is binding, then picks the optimal strategy:
  - *QualityFirst* path: 1–2 encodes to hit the quality floor (used when there's no limit or the limit is generous)
  - *SizeConstrained* path: binary-searches with skip-impossible-resolutions guards (used when the limit is tight)
- **Live progress feedback** — per-file ETA, MB/min throughput, a progress bar for the whole benchmark, and pre-flight skip when a planned pass is provably going to fail
- **Resume support** — re-running a batch skips files whose output already exists and isn't stale (instead of duplicating them as `_compressed_2.mp4`)
- **Clean Ctrl+C** — actively kills child ffmpeg processes and sweeps leftover tmp files instead of leaving orphans behind
- **Input lockout** — keystrokes typed during an encode no longer skip past important prompts

---

## Install

Grab the build for your platform from the [Releases](https://codeberg.org/Mitzingdash/smartcompress/releases) page.

### Windows

1. Download `SmartCompress-v3.1.0-win-x64.zip`.
2. Extract anywhere — Desktop, USB stick, `C:\Tools\`, doesn't matter. It's fully portable.
3. Double-click `SmartCompress.exe`.

### Linux

```bash
tar -xzf SmartCompress-v3.1.0-linux-x64.tar.gz -C ~/Apps/smartcompress
cd ~/Apps/smartcompress
chmod +x SmartCompress
./SmartCompress
```

If you already have ffmpeg installed (most distros), SmartCompress will pick it up from your `PATH` and skip the download.

### macOS

```bash
tar -xzf SmartCompress-v3.1.0-osx-arm64.tar.gz -C ~/Apps/smartcompress    # Apple Silicon
# or
tar -xzf SmartCompress-v3.1.0-osx-x64.tar.gz -C ~/Apps/smartcompress      # Intel Mac

cd ~/Apps/smartcompress
chmod +x SmartCompress
xattr -d com.apple.quarantine SmartCompress    # let Gatekeeper run the unsigned binary
./SmartCompress
```

First launch downloads ffmpeg (~75 MB) next to the binary, **unless** ffmpeg is already on your `PATH` (Homebrew, apt, etc.) — in which case the bundled download is skipped.

> No installer, no PATH changes, no admin rights. Delete the folder to uninstall.

---

## How to use it

### Compress mode

```
1. Input            drag a file OR a folder into the window
2. Preview table    shows every video found, with res / duration / size / complexity
3. Preset           Discord Free, Nitro, Smallest Possible, or Custom MB
4. Encoder          recommended pick is highlighted; you can override
5. Resolution       Auto (smart ladder) or pick a specific one
6. Output folder    defaults to ./out next to the exe
7. Confirm          press Enter; it runs the whole batch
```

The wizard tells you up-front what it'll do and what the cost will be. Live ETA between files based on actual throughput so far — no static "1 hour for 5 videos" lies.

### Benchmark mode

Optional but **highly recommended** the first time you use it on new hardware.

```
1. Pick "Run benchmark" from the start menu
2. Add 2+ varied clips (or drop a folder — it'll pick them out)
3. Fast (~5-10 min) or Accurate (~30 min) mode
4. Walk away. Come back to a populated reference cache.
```

The benchmark sweeps your GPU encoder(s) across a range of CQPs at four resolutions, measures each output's SSIM, and stores the data. Future compressions read this cache to pick the right starting CQP on the first try — meaning most files finish in **one pass** instead of 3-5.

A progress bar at the bottom shows total encodes done, percent complete, and a live ETA that refines as it runs.

---

## Presets

| Preset | Size limit | Codec default |
|---|---|---|
| Discord Free | 10 MB | H.264 |
| Discord Nitro Basic | 25 MB | H.264 |
| Discord Nitro | 500 MB | H.264 |
| Smallest Possible | No limit | Best available |
| Custom | You decide | Best available |

The limit is a **ceiling, not a goal.** SmartCompress targets the smallest great-looking file it can produce — it won't pad a 2 MB clip to 500 MB just because the preset allows it.

### Why H.264 by default for Discord?

H.264 plays inline in Discord chat. H.265 (HEVC) forces a download button for some users instead of playing. Picking H.265 is fine if you know your audience, but H.264 is the safe default.

---

## What it actually does under the hood

### The two paths, in plain English

Old approach (every other tool): binary-search through CQP values until you find the highest one that still meets quality. Always 3–5 passes regardless of context.

**SmartCompress approach:** *before* any encoding, the Estimator asks the reference cache two questions:

1. *What CQP would hit my quality floor for this content?*
2. *What CQP would fit my size limit for this content?*

Then it compares the answers:

- **Quality CQP ≥ size CQP**: the limit is non-binding. Just go for quality. **1 pass.**
- **Quality CQP ≈ size CQP**: limit is binding but reasonable. Binary search. **2–3 passes.**
- **Quality CQP ≪ size CQP**: the limit is so tight that hitting quality at this resolution is impossible. **Drop a resolution step before starting.**

### The reference cache (CQP cache)

Every encode you do — and every benchmark run — adds a `(content fingerprint, encoder, resolution, CQP) → (bytes, SSIM)` data point. The cache file lives next to the exe as `cqp_cache.json` (capped at 2 MB) and `benchmark_cache.json` (uncapped, populated by benchmark mode and never pruned).

When a new clip comes in, SmartCompress fingerprints it (adaptive complexity profile, duration-weighted bits-per-pixel-per-frame), finds the closest matches in the cache, and projects what CQP will hit your target. Multi-reference weighted averaging smooths out any individual cache entry's quirks.

### Self-calibration

After every real encode, SmartCompress records the difference between what it predicted and what actually happened. Once it has 5+ samples per encoder, it shifts future predictions by the median residual — so if your specific GPU consistently runs 1 CQP "tighter" than the formula expects, it just learns that and stops making the same mistake.

### Quality measurement

Every quality-relevant pass is scored with **SSIM** (Structural Similarity Index). Comparison is resolution-normalized — dropping to 720p doesn't fake a perfect score just because the frames are smaller.

| Content | SSIM floor |
|---|---|
| Simple | 0.95 |
| Medium | 0.93 |
| Complex (gameplay, fast motion) | 0.96 |

### Resolution ladder

If quality falls below the floor at the current resolution, SmartCompress steps down rather than giving up:

```
original → 1080p → 720p → 540p → 480p → 360p
```

For most fast-motion gameplay, locking to 720p often looks sharper than heavily-compressed 1080p.

---

## Config

Everything tunable lives in `config.json` next to the `.exe`. Edit it directly — no rebuild needed.

```json
{
  "version": "3.1.0",
  "ssim_floors":  { "Simple": 0.95, "Medium": 0.93, "Complex": 0.96 },
  "default_cqp":  { "hevc_amf": 28, "h264_amf": 23, ... },
  "max_cqp":      { "h264_amf": 45, ... },
  "resolution_steps": [2160, 1440, 1080, 720, 540, 480, 360]
}
```

See `config.json` in the release for the full list (presets, encoder labels, SSIM bands, min-output-height rules).

---

## Roadmap

### Done
- [x] Full C# / Spectre.Console rewrite, single-file portable binary
- [x] Hardware encoder detection (test-encode, not compile-time probe)
- [x] CQP cache with adaptive complexity fingerprinting
- [x] Two-path Estimator (QualityFirst vs SizeConstrained)
- [x] Benchmark mode (Fast / Accurate)
- [x] Self-calibration: per-encoder bias correction from real-world residuals
- [x] Per-encoder slope `k` fitted at runtime from cache data
- [x] Multi-reference weighted averaging across the top-N similar clips
- [x] Cross-validation pass after every benchmark (honest predictor accuracy report)
- [x] Batch mode with folder input, per-file preview, skip-existing on resume
- [x] Live ETA + benchmark progress bar
- [x] Clean Ctrl+C cancellation
- [x] Input lockout (keystrokes during encodes can't skip prompts)
- [x] Cross-platform builds — Windows, Linux, macOS (Intel + Apple Silicon)
- [x] VideoToolbox support (macOS hardware encoding)
- [x] System ffmpeg auto-detection

### Up next (3.2.0)
- [ ] VAAPI hardware encoding for Linux AMD users
- [ ] Wizard rework — restructure to take full advantage of the batch flow
- [ ] Per-video config step (optional toggle: pick encoder/res per file, or stay auto)

### Then
- [ ] Image pipeline — WebP / AVIF / SVG vectorization
- [ ] Audio pipeline — Opus / AAC re-encode, passthrough option
- [ ] Community lookup table (opt-in crowdsourced encode data)

### Later
- [ ] Avalonia GUI
- [ ] Neural network on top of the lookup table

---

## What this isn't

- Not a cloud tool — everything runs on your machine, nothing gets uploaded
- Not a codec — it's an orchestration layer on top of ffmpeg
- Not a replacement for HandBrake if you want manual control over every knob — this is for everyone else

---

## Old Python version

The original Python prototype is preserved in the [`old`](https://codeberg.org/Mitzingdash/smartcompress/src/branch/old) branch of this repo for reference. It is unmaintained — all new work happens against the C# tree on `main`.

---

## Credits

Made by [Mitzingdash](https://codeberg.org/Mitzingdash) — solo project, weekend hobby scale.

Made utilising AI assistance for parts of the rewrite (predictor math, refactoring, docs).

## License

MIT — see [LICENSE](LICENSE) for the full text.
