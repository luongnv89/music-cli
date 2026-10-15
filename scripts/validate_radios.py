#!/usr/bin/env python3
"""Check that every bundled radio stream actually plays.

Decodes a few seconds of audio from each URL in ``Config.DEFAULT_RADIOS`` and
the mood/time maps with ffmpeg (the same decoder ffplay uses), so a station
only passes if it serves real audio, not just an HTTP 200.

Usage: .venv/bin/python scripts/validate_radios.py [--seconds N] [--workers N]
Exits 1 if any stream fails. Needs network access and ffmpeg on PATH.
"""

import argparse
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from music_cli.config import Config

TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


def default_streams() -> list[tuple[str, str]]:
    """Return (name, url) for every bundled station plus mood/time map URLs."""
    streams: list[tuple[str, str]] = []
    for line in Config.DEFAULT_RADIOS.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, url = line.partition("|")
        streams.append((name.strip(), (url or name).strip()))
    known = {url for _, url in streams}
    for key in ("mood_radio_map", "time_radio_map"):
        for label, url in Config.DEFAULT_CONFIG[key].items():  # type: ignore[attr-defined]
            if url not in known:
                streams.append((f"{key}:{label}", url))
                known.add(url)
    return streams


def check_stream(url: str, seconds: float) -> tuple[bool, str]:
    """Decode ``seconds`` of audio from ``url``; return (ok, detail)."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-rw_timeout", "15000000",
        "-i", url, "-t", str(seconds + 1), "-vn", "-f", "null", "-",
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=seconds + 40)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    err = proc.stderr.decode("utf-8", "replace")
    times = TIME_RE.findall(err)
    decoded = 0.0
    if times:
        h, m, s = times[-1]
        decoded = int(h) * 3600 + int(m) * 60 + float(s)
    if proc.returncode == 0 and decoded >= seconds:
        return True, f"decoded {decoded:.1f}s"
    last = next((ln for ln in reversed(err.splitlines()) if ln.strip()), "no output")
    return False, f"rc={proc.returncode} decoded={decoded:.1f}s: {last.strip()[:120]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=5.0, help="audio to decode per stream")
    parser.add_argument("--workers", type=int, default=16, help="parallel checks")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 2

    streams = default_streams()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda s: check_stream(s[1], args.seconds), streams))

    failed = 0
    for (name, url), (ok, detail) in zip(streams, results, strict=True):
        if not ok:
            failed += 1
        print(f"{'OK  ' if ok else 'FAIL'}  {name:32}  {detail}  {url if not ok else ''}".rstrip())
    print(f"\n{len(streams) - failed}/{len(streams)} streams playable")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
