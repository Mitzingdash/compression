"""Appended session log. Call init() once per session, w() to write lines."""

import datetime
from pathlib import Path

_fh = None


def init(out_dir: Path) -> None:
    global _fh
    close()
    out_dir.mkdir(parents=True, exist_ok=True)
    _fh = (out_dir / "compress.log").open("a", encoding="utf-8")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _fh.write(f"\n{'=' * 52}\n  {stamp}\n{'=' * 52}\n")
    _fh.flush()


def w(text: str) -> None:
    if _fh:
        _fh.write(text + "\n")
        _fh.flush()


def close() -> None:
    global _fh
    if _fh:
        _fh.close()
        _fh = None
