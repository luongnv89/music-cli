"""Abstract taste profile extracted from a local playlist.

Given a playlist file (M3U / PLS), probe every audio asset with ffprobe and
aggregate *abstract* attributes only — tempo histogram, key distribution,
dynamic range, and mean loudness.  Artist names, track titles, and file paths
never appear in the returned profile.

The profile is consumed by ``mc studio build --from-playlist`` to seed the
``taste_profile`` field of the :class:`~music_cli.studio.schemas.Constitution`.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .trace import _sha256

# ---------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------


@dataclass
class TasteProfile:
    """Abstract taste profile — no string fields naming tracks or artists.

    Every field is numeric or a distribution derived from ffprobe analysis.
    The profile is serialisable to a plain dict so it can be stored in the
    Constitution's ``taste_profile`` slot.
    """

    #: Histogram of tempo buckets (BPM ranges). Each bin counts how many
    #: tracks fell into that range.
    tempo_histogram: list[int] = field(default_factory=list)

    #: Key distribution — keys are ICPF key labels (``C``, ``Cm``, ``D``, …)
    #: and values are normalised frequencies in ``[0, 1]``.
    key_distribution: dict[str, float] = field(default_factory=dict)

    #: Mean dynamic range in dB across all tracks.
    mean_dynamic_range_db: float = 0.0

    #: Mean perceived loudness in dB LUFS across all tracks.
    mean_loudness_db: float = 0.0

    #: Number of tracks analysed (for diagnostics).
    track_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tempo_histogram": list(self.tempo_histogram),
            "key_distribution": dict(self.key_distribution),
            "mean_dynamic_range_db": self.mean_dynamic_range_db,
            "mean_loudness_db": self.mean_loudness_db,
            "track_count": self.track_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TasteProfile:
        return cls(
            tempo_histogram=data.get("tempo_histogram", []),
            key_distribution=data.get("key_distribution", {}),
            mean_dynamic_range_db=float(data.get("mean_dynamic_range_db", 0.0)),
            mean_loudness_db=float(data.get("mean_loudness_db", 0.0)),
            track_count=int(data.get("track_count", 0)),
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"TasteProfile(tracks={self.track_count}, "
            f"loudness={self.mean_loudness_db:.1f} dB, "
            f"dyn_range={self.mean_dynamic_range_db:.1f} dB)"
        )


# ---------------------------------------------------------------------------
# playlist parsing
# ---------------------------------------------------------------------------


def _parse_m3u(text: str) -> list[str]:
    """Return audio file paths from an M3U (extended or classic) text.

    Skips all metadata lines (starting with ``#``) and returns every
    remaining non-empty line as a path candidate.
    """
    paths: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            paths.append(stripped)
    return paths


def _parse_pls(text: str) -> list[str]:
    """Return audio file paths from a PLS playlist text.

    Looks for ``File1``, ``File2``, … keys and returns their values.
    """
    paths: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("file") and "=" in line:
            key, _, value = line.partition("=")
            val = value.strip()
            if val and val.startswith("http"):
                paths.append(val)
    return paths


def _guess_format(path: Path) -> str:
    """Heuristic: ``.m3u8`` / ``.m3u`` → ``m3u``, ``.pls`` → ``pls``, else ``m3u``."""
    suffix = path.suffix.lower()
    if suffix in (".m3u", ".m3u8"):
        return "m3u"
    if suffix == ".pls":
        return "pls"
    return "m3u"  # default fallback


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------


def _run_ffprobe(filepath: str, fmt: str) -> dict[str, Any]:
    """Run ffprobe and return parsed JSON output.

    Raises ``FFProbeError`` when ffprobe is unavailable or returns non-zero.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise FFProbeError(f"ffprobe not found: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FFProbeError(f"ffprobe timed out for {filepath}") from exc
    if result.returncode != 0:
        raise FFProbeError(f"ffprobe returned {result.returncode}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FFProbeError(f"ffprobe produced invalid JSON: {exc}") from exc


class FFProbeError(RuntimeError):
    """ffprobe failed for a single file."""


# ---------------------------------------------------------------------------
# attribute extraction
# ---------------------------------------------------------------------------


def _extract_tempo(probe: dict[str, Any]) -> float | None:
    """Best-effort tempo (BPM) from ffprobe metadata.

    Checks ``TAG:tempo``, ``TAG:BPM``, and ``TAG:genre`` heuristics.
    Returns None when no tempo metadata is available.
    """
    tags = probe.get("format", {}).get("tags", {}) or probe.get("streams", [{}])[0].get("tags", {})
    for key in ("tempo", "bpm"):
        val = tags.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    # Heuristic: some tags embed BPM in genre/description
    for val in tags.values():
        if isinstance(val, str):
            import re
            m = re.search(r"(\d{2,3})\s*bpm", val, re.IGNORECASE)
            if m:
                return float(m.group(1))
    return None


def _extract_key(probe: dict[str, Any]) -> str | None:
    """Best-effort musical key from ffprobe TAG:KEY or similar.

    Normalises to ICPF-style labels: ``C``, ``Cm``, ``D``, ``Dm``, ``E``,
    ``F``, ``Fm``, ``G``, ``Gm``, ``A``, ``Am``, ``B``, ``Bm``.
    """
    tags = probe.get("format", {}).get("tags", {}) or probe.get("streams", [{}])[0].get("tags", {})
    for key in ("key", "original_key", "musical_key"):
        val = tags.get(key)
        if val is not None:
            import re
            m = re.match(r"([A-Ga-g])([#b])?(m)?", val.strip())
            if m:
                root = m.group(1).upper()
                accidental = m.group(2) or ""
                mode = m.group(3) or ""
                label = f"{root}{accidental}{mode}"
                if label in {"C", "Cm", "D", "Dm", "E", "F", "Fm", "G", "Gm", "A", "Am", "B", "Bm"}:
                    return label
    return None


def _extract_dynamic_range(probe: dict[str, Any]) -> float | None:
    """Mean dynamic range (Loudness Range) in dB from EBU R128 metadata.

    Checks ``TAG:R128_REFERENCE_LOUDNESS``, ``TAG:R128_RANGE``, and
    stream-level ``TAG:R128_RANGE``. Returns None when unavailable.
    """
    # Check format-level tags first
    fmt_tags = probe.get("format", {}).get("tags", {})
    for key in ("r128_range", "R128_RANGE"):
        val = fmt_tags.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    # Check stream-level tags
    for stream in probe.get("streams", []):
        st_tags = stream.get("tags", {})
        for key in ("r128_range", "R128_RANGE"):
            val = st_tags.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
    # Fallback: compute from max and min peak amplitude if available
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "audio":
            tags = stream.get("tags", {})
            max_peak = tags.get("MAXPEAK") or tags.get("max_peak")
            min_peak = tags.get("MINPEAK") or tags.get("min_peak")
            if max_peak is not None and min_peak is not None:
                try:
                    max_db = 20 * math.log10(float(max_peak)) if float(max_peak) > 0 else -96.0
                    min_db = 20 * math.log10(float(min_peak)) if float(min_peak) > 0 else -96.0
                    return max_db - min_db
                except (ValueError, ZeroDivisionError):
                    pass
    return None


def _extract_loudness(probe: dict[str, Any]) -> float | None:
    """Perceived loudness (LUFS) from EBU R128 ``TAG:R128_LOUDNESS``.

    Returns None when unavailable.
    """
    fmt_tags = probe.get("format", {}).get("tags", {})
    for key in ("r128", "R128_LOUDNESS", "r128_loudness"):
        val = fmt_tags.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "audio":
            st_tags = stream.get("tags", {})
            for key in ("r128", "R128_LOUDNESS", "r128_loudness"):
                val = st_tags.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        pass
    return None


def _probe_file(filepath: str) -> dict[str, Any]:
    """Probe a single audio file and return its abstract attributes."""
    probe = _run_ffprobe(filepath, "json")
    return {
        "tempo": _extract_tempo(probe),
        "key": _extract_key(probe),
        "dynamic_range_db": _extract_dynamic_range(probe),
        "loudness_db": _extract_loudness(probe),
    }


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def from_playlist(path: str | Path) -> TasteProfile:
    """Extract an abstract :class:`TasteProfile` from a local playlist file.

    The playlist is parsed (M3U or PLS), each audio file is probed with
    ffprobe, and the abstract attributes are aggregated.  **No artist or
    track names are ever included** in the returned profile.

    Args:
        path: Path to the playlist file.

    Returns:
        A :class:`TasteProfile` with aggregated abstract attributes.

    Raises:
        OSError: When the playlist file cannot be read.
        FFProbeError: When ffprobe fails for any file (non-fatal — the file
            is skipped with a warning).
    """
    playlist_path = Path(path)
    if not playlist_path.exists():
        raise OSError(f"playlist file not found: {playlist_path}")

    text = playlist_path.read_text(encoding="utf-8")
    fmt = _guess_format(playlist_path)

    if fmt == "pls":
        file_paths = _parse_pls(text)
    else:
        file_paths = _parse_m3u(text)

    tempo_bins: list[int] = [0] * 10  # 10 bins: 60-70, 70-80, …, 150-160
    key_counts: dict[str, int] = {}
    dyn_ranges: list[float] = []
    loudness_vals: list[float] = []
    track_count = 0

    for fp in file_paths:
        # Resolve relative to the playlist directory
        candidate = playlist_path.parent / fp
        if not candidate.exists():
            candidate = Path(fp)
        if not candidate.exists():
            continue

        try:
            attrs = _probe_file(str(candidate))
        except FFProbeError:
            continue  # skip files that can't be probed

        track_count += 1

        # Tempo histogram — 10 bins from 60 to 160 BPM
        tempo = attrs.get("tempo")
        if tempo is not None and 60 <= tempo <= 160:
            bin_idx = min(int((tempo - 60) / 10), 9)
            tempo_bins[bin_idx] += 1

        # Key distribution
        key = attrs.get("key")
        if key is not None:
            key_counts[key] = key_counts.get(key, 0) + 1

        # Dynamic range
        dr = attrs.get("dynamic_range_db")
        if dr is not None:
            dyn_ranges.append(dr)

        # Loudness
        loud = attrs.get("loudness_db")
        if loud is not None:
            loudness_vals.append(loud)

    # Normalise key distribution to [0, 1]
    key_dist: dict[str, float] = {}
    if key_counts:
        total_keys = sum(key_counts.values())
        for k, v in key_counts.items():
            key_dist[k] = round(v / total_keys, 4)

    mean_dr = sum(dyn_ranges) / len(dyn_ranges) if dyn_ranges else 0.0
    mean_loud = sum(loudness_vals) / len(loudness_vals) if loudness_vals else 0.0

    return TasteProfile(
        tempo_histogram=tempo_bins,
        key_distribution=key_dist,
        mean_dynamic_range_db=round(mean_dr, 2),
        mean_loudness_db=round(mean_loud, 2),
        track_count=track_count,
    )


__all__ = ["FFProbeError", "TasteProfile", "from_playlist"]
