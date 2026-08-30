"""Video scene node with H3 budget protection and a static fallback.

``VideoNode`` owns one scene-sized MP4 under a studio project's ``nodes/``
directory.  H3 responses are downloaded through the same injectable downloader
used by the audio nodes and validated with the project's probe runner.  When
H3 is disabled, the node renders a captioned still image (or a generated
colour background) with ffmpeg instead.

The node deliberately stops at individual scene assets.  Joining scenes with
audio belongs to the P4.2 composition stage, while this module provides the
P4.1 asset and cost boundary that stage consumes.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import math
import shutil
import subprocess
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .base import BaseNode, NodeError, NodeLockedError
from .ffmpeg import DEFAULT_FFMPEG, MixNodeError, resolve_binary

#: Default maximum H3 spend for one build.
DEFAULT_BUILD_CAP = Decimal("1.00")
#: Conservative per-call estimate until provider billing data is available.
DEFAULT_H3_CALL_COST = Decimal("1.00")
#: Fixed output dimensions for generated still-video fallbacks.
DEFAULT_VIDEO_SIZE = "1280x720"
DEFAULT_VIDEO_FPS = 30

# Backwards-friendly aliases for callers that name the setting as a budget cap
# rather than a build cap.
DEFAULT_BUDGET_CAP = DEFAULT_BUILD_CAP
H3_CALL_COST = DEFAULT_H3_CALL_COST

DownloaderRunner = Callable[..., Any]
FfmpegRunner = Callable[..., Any]


def _decimal(value: Any, field: str) -> Decimal:
    """Convert a manifest or constructor amount without binary-float drift."""
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite non-negative number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite non-negative number") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return amount


def _manifest_dict(manifest: Any) -> Mapping[str, Any] | None:
    """Return a manifest mapping from a dict or a schema instance."""
    if manifest is None:
        return None
    if isinstance(manifest, Mapping):
        return manifest
    to_dict = getattr(manifest, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, Mapping):
            return data
    raise TypeError("manifest must be a mapping or expose to_dict()")


def _manifest_budget(manifest: Any) -> Mapping[str, Any] | None:
    """Read the optional ``budget`` block without depending on Pydantic."""
    data = _manifest_dict(manifest)
    if data is None:
        return None
    budget = data.get("budget")
    if budget is None:
        return None
    if not isinstance(budget, Mapping):
        raise ValueError("manifest.budget must be a mapping")
    return budget


def _manifest_cover_art(manifest: Any) -> str | None:
    """Read the plan's cover art path from a manifest when present."""
    data = _manifest_dict(manifest)
    if data is None:
        return None
    direct = data.get("cover_art")
    if isinstance(direct, str) and direct.strip():
        return direct
    plan = data.get("plan")
    if isinstance(plan, Mapping):
        value = plan.get("cover_art")
        if isinstance(value, str) and value.strip():
            return value
    return None


@dataclass(init=False)
class BuildBudget:
    """Mutable per-build H3 budget shared by all scene nodes.

    ``spent`` is reserved immediately before a paid H3 request.  It is not
    refunded when the provider or download later fails: the request may still
    be billable, and under-counting it would make a retry bypass the ceiling.
    """

    cap: Decimal
    spent: Decimal
    currency: str

    def __init__(
        self,
        cap: Decimal | int | float | str = DEFAULT_BUILD_CAP,
        spent: Decimal | int | float | str = Decimal("0"),
        currency: str = "USD",
    ) -> None:
        self.cap = _decimal(cap, "budget cap")
        self.spent = _decimal(spent, "budget spent")
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError("budget currency must be a non-empty string")
        self.currency = currency.strip()

    @classmethod
    def from_manifest(cls, manifest: Any) -> BuildBudget:
        """Build a budget from ``ProjectManifest.budget`` or use defaults."""
        budget = _manifest_budget(manifest)
        if budget is None:
            return cls()
        # ``per_build_cap`` is the issue-level setting.  ``cap`` remains
        # accepted for manifests produced by the earlier studio schema.
        cap = (
            budget["per_build_cap"]
            if "per_build_cap" in budget
            else budget.get("cap", DEFAULT_BUILD_CAP)
        )
        spent = budget.get("spent", 0)
        currency = budget.get("currency", "USD")
        return cls(cap=cap, spent=spent, currency=currency)

    @property
    def remaining(self) -> Decimal:
        """Return unspent budget; a confirmed overage is represented as negative."""
        return self.cap - self.spent

    def reserve(self, cost: Any, *, confirm: bool = False) -> Decimal:
        """Reserve one H3 call and return its projected total.

        Equality with the cap is allowed.  A caller must explicitly confirm
        only an over-cap projection; confirmation never turns accounting off.
        """
        amount = _decimal(cost, "H3 cost")
        projected = self.spent + amount
        if projected > self.cap and not confirm:
            raise BudgetExceeded(
                cap=self.cap,
                spent=self.spent,
                projected=projected,
                cost=amount,
                currency=self.currency,
            )
        self.spent = projected
        return projected


class BudgetExceeded(NodeError):  # noqa: N818
    """Raised before H3 is called when a build would exceed its cap."""

    def __init__(
        self,
        *,
        cap: Decimal,
        spent: Decimal,
        projected: Decimal,
        cost: Decimal,
        currency: str,
    ) -> None:
        self.cap = cap
        self.spent = spent
        self.projected = projected
        self.cost = cost
        self.currency = currency
        super().__init__(
            "H3 budget exceeded: "
            f"projected {currency} {projected:.2f} exceeds cap {currency} {cap:.2f}; "
            "pass --confirm to authorize the overage"
        )


def _url_from_value(value: Any) -> str | None:
    """Extract a media URL from the documented H3 response shapes."""
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith(("http://", "https://", "memory://")):
            return candidate
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                return _url_from_value(json.loads(candidate))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
        return None
    if isinstance(value, list):
        for item in value:
            found = _url_from_value(item)
            if found:
                return found
        return None
    if not isinstance(value, Mapping):
        return None
    for key in ("video_url", "url"):
        found = _url_from_value(value.get(key))
        if found:
            return found
    for key in ("media_urls", "content", "text", "data", "result"):
        found = _url_from_value(value.get(key))
        if found:
            return found
    return None


def _video_url(result: Any) -> str:
    """Pull a usable video URL from an H3 result or raise a safe error."""
    url = _url_from_value(result)
    if not url:
        raise NodeError("h3_generate returned no usable video URL")
    return url


def _duration(value: Any) -> float:
    """Validate a scene duration before spending budget or invoking a tool."""
    if isinstance(value, bool):
        raise NodeError("video duration must be a finite number greater than zero")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise NodeError("video duration must be a finite number greater than zero") from exc
    if not math.isfinite(result) or result <= 0:
        raise NodeError("video duration must be a finite number greater than zero")
    return result


class VideoNode(BaseNode):
    """Generate one H3 scene or a captioned static fallback.

    ``generate(prompt, duration)`` is intentionally compatible with the
    positional shape used by the P4 node contract.  Pass one ``BuildBudget``
    instance to each scene node in a build so all H3 calls share its spend.
    """

    FILENAME_STEM = "scene"
    EXTENSION = ".mp4"
    DEFAULT_COST = DEFAULT_H3_CALL_COST

    def __init__(
        self,
        adapter: Any,
        *,
        proj_dir: str | Path,
        budget: BuildBudget | Mapping[str, Any] | Decimal | int | float | str | None = None,
        manifest: Any | None = None,
        project_manifest: Any | None = None,
        estimated_cost: Decimal | int | float | str = DEFAULT_H3_CALL_COST,
        cost_per_call: Decimal | int | float | str | None = None,
        h3_cost: Decimal | int | float | str | None = None,
        budget_cap: Decimal | int | float | str | None = None,
        confirm: bool = False,
        no_h3: bool = False,
        cover_art: str | Path | None = None,
        ffmpeg: str | Path | None = None,
        ffmpeg_runner: FfmpegRunner | None = None,
        downloader: Any | None = None,
        probe: Callable[[Path], dict[str, Any]] | None = None,
        probe_runner: Callable[[Path], dict[str, Any]] | None = None,
    ) -> None:
        if manifest is not None and project_manifest is not None:
            raise TypeError("pass either manifest or project_manifest, not both")
        if manifest is None:
            manifest = project_manifest
        if probe is None:
            probe = probe_runner
        super().__init__(
            adapter,
            proj_dir=proj_dir,
            downloader=downloader,
            probe=probe,
        )
        self._manifest_budget_block: MutableMapping[str, Any] | None = None
        if budget is None:
            existing_budget = getattr(manifest, "_video_build_budget", None)
            if isinstance(existing_budget, BuildBudget):
                self.budget = existing_budget
            elif budget_cap is not None:
                manifest_budget = _manifest_budget(manifest)
                self.budget = BuildBudget(
                    cap=budget_cap,
                    spent=manifest_budget.get("spent", 0) if manifest_budget else 0,
                    currency=manifest_budget.get("currency", "USD") if manifest_budget else "USD",
                )
            else:
                self.budget = BuildBudget.from_manifest(manifest)
            manifest_budget = _manifest_budget(manifest)
            if isinstance(manifest_budget, MutableMapping):
                self._manifest_budget_block = manifest_budget
            if manifest is not None and not isinstance(manifest, Mapping):
                try:
                    manifest._video_build_budget = self.budget
                except (AttributeError, TypeError):
                    pass
        elif isinstance(budget, BuildBudget):
            self.budget = budget
        elif isinstance(budget, Mapping):
            self.budget = BuildBudget(
                cap=budget["per_build_cap"]
                if "per_build_cap" in budget
                else budget.get("cap", DEFAULT_BUILD_CAP),
                spent=budget.get("spent", 0),
                currency=budget.get("currency", "USD"),
            )
        elif isinstance(budget, (Decimal, int, float, str)):
            self.budget = BuildBudget(cap=budget)
        else:
            raise TypeError("budget must be a BuildBudget, amount, or mapping")

        selected_cost = (
            cost_per_call
            if cost_per_call is not None
            else h3_cost
            if h3_cost is not None
            else estimated_cost
        )
        self.estimated_cost = _decimal(selected_cost, "H3 cost")
        self.confirm = bool(confirm)
        self.no_h3 = bool(no_h3)
        self.cover_art = str(cover_art) if cover_art is not None else None
        self._ffmpeg = str(ffmpeg) if ffmpeg is not None else None
        self._ffmpeg_runner = ffmpeg_runner
        self._manifest = manifest

    def _refresh_manifest_spend(self) -> None:
        """Pick up spend reserved by another node sharing this manifest."""
        if self._manifest_budget_block is not None and "spent" in self._manifest_budget_block:
            self.budget.spent = _decimal(self._manifest_budget_block["spent"], "budget spent")

    def _sync_manifest_spend(self) -> None:
        """Mirror reserved spend into a mutable ProjectManifest budget block."""
        if self._manifest_budget_block is not None:
            self._manifest_budget_block["spent"] = float(self.budget.spent)

    async def _synthesize(self, prompt: str, duration: float) -> tuple[str, Path]:
        """Call H3 and return its media URL plus the scene destination."""
        result = await self.adapter.h3_generate(prompt, duration=duration)
        return _video_url(result), self._next_path()

    async def generate(
        self,
        prompt: str,
        duration: float,
        *,
        caption: str | None = None,
        cover_art: str | Path | None = None,
        confirm: bool | None = None,
        no_h3: bool | None = None,
    ) -> Path:
        """Generate and probe ``nodes/scene-N.mp4``.

        H3 spend is reserved immediately before the adapter call.  The static
        path neither calls H3 nor changes the budget, and can be selected per
        call with ``no_h3=True`` or for the whole node in the constructor.
        """
        if self._locked:
            raise NodeLockedError("scene: locked; call unlock() before regenerating")
        if not isinstance(prompt, str) or not prompt.strip():
            raise NodeError("video prompt must be a non-empty string")
        scene_duration = _duration(duration)
        use_fallback = self.no_h3 if no_h3 is None else bool(no_h3)
        destination: Path

        if use_fallback:
            destination = self._next_path()
            selected_art = cover_art if cover_art is not None else self.cover_art
            if selected_art is None:
                selected_art = _manifest_cover_art(self._manifest)
            self._render_static(
                destination,
                scene_duration,
                caption=caption if caption is not None else prompt,
                cover_art=selected_art,
            )
        else:
            use_confirm = self.confirm if confirm is None else bool(confirm)
            # This is deliberately before _synthesize: a blocked projection
            # must not invoke the provider or create a partial output.
            self._refresh_manifest_spend()
            self.budget.reserve(self.estimated_cost, confirm=use_confirm)
            self._sync_manifest_spend()
            url, destination = await self._synthesize(prompt, scene_duration)
            self._nodes_dir.mkdir(parents=True, exist_ok=True)
            try:
                await self._downloader(url, destination)
            except asyncio.CancelledError:
                self._remove_output(destination)
                self._path = None
                raise
            except Exception as exc:
                self._remove_output(destination)
                self._path = None
                raise NodeError(f"scene: could not download H3 output: {exc}") from exc

        return self._finish(destination)

    def _finish(self, destination: Path) -> Path:
        """Probe, clean up failures, and lock a completed scene."""
        self._path = destination
        try:
            report = self._probe(destination)
        except asyncio.CancelledError:
            self._remove_output(destination)
            self._path = None
            raise
        except Exception as exc:
            self._remove_output(destination)
            self._path = None
            raise NodeError(f"scene: probe failed for {destination}: {exc}") from exc
        if not report.get("ok"):
            self._remove_output(destination)
            self._path = None
            raise NodeError(f"scene: probe failed for {destination}")
        self._locked = True
        return destination

    def _resolve_cover_art(self, value: str | Path | None) -> Path | None:
        """Resolve only an existing local regular file as cover art."""
        if value is None:
            return None
        raw = Path(value).expanduser()
        candidates = [raw]
        if not raw.is_absolute():
            candidates.extend((self.project_dir / raw, Path.cwd() / raw))
        seen: set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                if resolved.is_file():
                    return resolved
            except OSError:
                continue
        return None

    @staticmethod
    def _caption_filter(caption_file: Path, *, scale: bool) -> str:
        """Build a drawtext filter that contains no user caption text."""
        steps = []
        if scale:
            steps.append("scale=1280:720:force_original_aspect_ratio=decrease")
            steps.append("pad=1280:720:(ow-iw)/2:(oh-ih)/2")
        # The path is a generated basename and the process cwd is nodes_dir;
        # prompt/caption contents live in the text file, never in this graph.
        steps.append(
            f"drawtext=textfile={caption_file.name}:expansion=none:"
            "fontcolor=white:fontsize=36:box=1:boxcolor=black@0.6:"
            "boxborderw=12:x=(w-text_w)/2:y=h-text_h-40"
        )
        return ",".join(steps)

    def _static_command(
        self,
        ffmpeg_bin: str,
        destination: Path,
        duration: float,
        caption_file: Path,
        cover: Path | None,
    ) -> list[str]:
        """Return a shell-free ffmpeg argv for a still scene."""
        seconds = f"{duration:.6f}"
        cmd = [ffmpeg_bin, "-nostdin", "-y", "-v", "error"]
        if cover is not None:
            cmd.extend(["-loop", "1", "-i", str(cover)])
        else:
            cmd.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=black:s={DEFAULT_VIDEO_SIZE}:r={DEFAULT_VIDEO_FPS}:d={seconds}",
                ]
            )
        cmd.extend(
            [
                "-t",
                seconds,
                "-vf",
                self._caption_filter(caption_file, scale=cover is not None),
                "-an",
                "-r",
                str(DEFAULT_VIDEO_FPS),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(destination.resolve()),
            ]
        )
        return cmd

    def _image_fallback_command(
        self,
        binary: str,
        caption_file: Path,
        image_path: Path,
        cover: Path | None,
    ) -> list[str]:
        """Return ImageMagick argv for a captioned PNG fallback."""
        font_candidates = (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        )
        font = next((path for path in font_candidates if path.is_file()), None)
        command = [binary]
        if cover is None:
            command.extend(["-size", DEFAULT_VIDEO_SIZE, "xc:black"])
        else:
            command.extend(
                [
                    str(cover.resolve()),
                    "-resize",
                    f"{DEFAULT_VIDEO_SIZE}^",
                    "-gravity",
                    "center",
                    "-crop",
                    f"{DEFAULT_VIDEO_SIZE}+0+0",
                    "+repage",
                ]
            )
        if font is not None:
            command.extend(["-font", str(font)])
        command.extend(
            [
                "-fill",
                "white",
                "-gravity",
                "center",
                "-pointsize",
                "36",
                f"caption:@{str(caption_file.resolve())}",
                "-flatten",
                str(image_path.resolve()),
            ]
        )
        return command

    def _render_image_fallback(
        self,
        destination: Path,
        duration: float,
        caption_file: Path,
        cover: Path | None,
    ) -> None:
        """Render a caption image when drawtext is unavailable."""
        binary = shutil.which("magick") or shutil.which("convert")
        if binary is None:
            raise NodeError("scene: no ImageMagick caption fallback is available")
        image_path = self._nodes_dir / f"{destination.stem}.png"
        command = self._image_fallback_command(binary, caption_file, image_path, cover)
        try:
            result = subprocess.run(
                command,
                cwd=self._nodes_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise NodeError(f"scene: image caption fallback failed to start: {exc}") from exc
        if result.returncode != 0 or not image_path.exists():
            detail = (result.stderr or result.stdout or "no stderr").strip()
            raise NodeError(f"scene: image caption fallback failed: {detail[-500:]}")
        try:
            ffmpeg_bin = self._ffmpeg or DEFAULT_FFMPEG
            self._run_ffmpeg(
                self._still_image_command(ffmpeg_bin, destination, duration, image_path)
            )
            if not destination.exists():
                raise NodeError("scene: ffmpeg image fallback produced no output")
        except NodeError:
            self._remove_output(destination)
            raise

    def _still_image_command(
        self,
        ffmpeg_bin: str,
        destination: Path,
        duration: float,
        image_path: Path,
    ) -> list[str]:
        """Return an ffmpeg argv for a captioned still-image fallback."""
        seconds = f"{duration:.6f}"
        return [
            ffmpeg_bin,
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-loop",
            "1",
            "-i",
            str(Path(image_path).resolve()),
            "-t",
            seconds,
            "-an",
            "-r",
            str(DEFAULT_VIDEO_FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(destination.resolve()),
        ]

    def _color_fallback_command(
        self,
        ffmpeg_bin: str,
        destination: Path,
        duration: float,
    ) -> list[str]:
        """Return ffmpeg argv for a plain colour video (no drawtext)."""
        seconds = f"{duration:.6f}"
        return [
            ffmpeg_bin,
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={DEFAULT_VIDEO_SIZE}:r={DEFAULT_VIDEO_FPS}:d={seconds}",
            "-t",
            seconds,
            "-r",
            str(DEFAULT_VIDEO_FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(destination.resolve()),
        ]

    def _render_color_fallback(self, destination: Path, duration: float) -> None:
        """Render a plain black video when all caption renderers fail."""
        ffmpeg_bin = self._ffmpeg or DEFAULT_FFMPEG
        self._run_ffmpeg(self._color_fallback_command(ffmpeg_bin, destination, duration))
        if not destination.exists():
            raise NodeError("scene: ffmpeg colour fallback produced no output")

    @staticmethod
    def _write_caption_svg(path: Path, caption: str, cover: Path | None = None) -> None:
        """Write a self-contained caption card without putting text in argv."""
        lines = [html.escape(line) for line in caption.splitlines()] or [""]
        tspans = "".join(
            f'<tspan x="640" dy="{48 if index else 0}">{line}</tspan>'
            for index, line in enumerate(lines)
        )
        background = '<rect width="1280" height="720" fill="#000000"/>'
        if cover is not None:
            try:
                encoded = base64.b64encode(cover.read_bytes()).decode("ascii")
            except OSError:
                encoded = ""
            if encoded:
                suffix = cover.suffix.lower().lstrip(".") or "png"
                background = (
                    f'<image href="data:image/{html.escape(suffix)};base64,{encoded}" '
                    'width="1280" height="720" preserveAspectRatio="xMidYMid slice"/>'
                )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
            f"{background}"
            '<text x="640" y="340" fill="#ffffff" font-size="36" '
            'font-family="sans-serif" text-anchor="middle">'
            f"{tspans}</text></svg>"
        )
        path.write_text(svg, encoding="utf-8")

    def _render_svg_fallback(
        self,
        destination: Path,
        duration: float,
        caption: str,
        cover: Path | None = None,
    ) -> None:
        """Render a caption card when the local ffmpeg lacks drawtext."""
        svg_path = self._nodes_dir / f"{destination.stem}.svg"
        self._write_caption_svg(svg_path, caption, cover=cover)
        ffmpeg_bin = self._ffmpeg or DEFAULT_FFMPEG
        # First try direct SVG input (works when ffmpeg has librsvg).
        try:
            self._run_ffmpeg(self._still_image_command(ffmpeg_bin, destination, duration, svg_path))
            if not destination.exists():
                raise NodeError("scene: ffmpeg SVG fallback produced no output")
            return
        except NodeError:
            self._remove_output(destination)
            # Fall through to PNG conversion below.
        # Convert SVG to PNG via ImageMagick so ffmpeg can read it without librsvg.
        png_path = self._nodes_dir / f"{destination.stem}-svg.png"
        try:
            binary = shutil.which("magick") or shutil.which("convert")
            if binary is None:
                raise NodeError("scene: no ImageMagick binary for SVG conversion")
            # magick SVG -> PNG (flatten to remove alpha)
            cmd = [binary, str(svg_path.resolve()), "-background", "black", "-flatten", str(png_path.resolve())]
            result = subprocess.run(
                cmd, cwd=self._nodes_dir, capture_output=True, text=True, check=False
            )
            if result.returncode != 0 or not png_path.exists():
                detail = (result.stderr or result.stdout or "no stderr").strip()
                raise NodeError(f"scene: SVG to PNG conversion failed: {detail[-500:]}")
            self._run_ffmpeg(self._still_image_command(ffmpeg_bin, destination, duration, png_path))
            if not destination.exists():
                raise NodeError("scene: ffmpeg SVG fallback produced no output")
        except NodeError:
            self._remove_output(destination)
            raise
        finally:
            self._remove_output(png_path)

    def _run_ffmpeg(self, command: list[str]) -> None:
        """Run an injected or real ffmpeg process without invoking a shell."""
        if self._ffmpeg_runner is not None:
            try:
                result = self._ffmpeg_runner(command, cwd=self._nodes_dir)
            except TypeError as first_error:
                # A one-argument runner is convenient in focused unit tests.
                try:
                    result = self._ffmpeg_runner(command)
                except TypeError:
                    raise first_error from None
            returncode = getattr(result, "returncode", result if isinstance(result, int) else 0)
            stderr = getattr(result, "stderr", "") or ""
        else:
            try:
                ffmpeg_bin = command[0]
                if self._ffmpeg is None:
                    ffmpeg_bin = resolve_binary(DEFAULT_FFMPEG)
                    command = [ffmpeg_bin, *command[1:]]
                result = subprocess.run(
                    command,
                    cwd=self._nodes_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except (MixNodeError, OSError, ValueError) as exc:
                raise NodeError(f"scene: ffmpeg failed to start: {exc}") from exc
            returncode = result.returncode
            stderr = result.stderr or result.stdout or ""
        if returncode != 0:
            detail = str(stderr).strip() or "no stderr"
            raise NodeError(f"scene: ffmpeg fallback failed: {detail[-500:]}")

    def _render_static(
        self,
        destination: Path,
        duration: float,
        *,
        caption: str,
        cover_art: str | Path | None,
    ) -> None:
        """Render cover art or a generated colour background with a caption."""
        self._nodes_dir.mkdir(parents=True, exist_ok=True)
        caption_file = self._nodes_dir / f"caption-{destination.stem.split('-')[-1]}.txt"
        caption_file.write_text(caption, encoding="utf-8")
        cover = self._resolve_cover_art(cover_art)
        ffmpeg_bin = self._ffmpeg or DEFAULT_FFMPEG
        auxiliary = (
            caption_file,
            self._nodes_dir / f"{destination.stem}.png",
            self._nodes_dir / f"{destination.stem}.svg",
        )

        try:
            try:
                self._run_ffmpeg(
                    self._static_command(
                        ffmpeg_bin,
                        destination,
                        duration,
                        caption_file,
                        cover,
                    )
                )
                if not destination.exists():
                    raise NodeError("scene: ffmpeg fallback produced no output")
                return
            except NodeError:
                self._remove_output(destination)

            # A present cover can be corrupt or unsupported.  A generated
            # colour visual keeps the no-H3 path usable without fetching an
            # arbitrary remote asset.
            if cover is not None:
                try:
                    self._run_ffmpeg(
                        self._static_command(
                            ffmpeg_bin,
                            destination,
                            duration,
                            caption_file,
                            None,
                        )
                    )
                    if not destination.exists():
                        raise NodeError("scene: ffmpeg fallback produced no output")
                    return
                except NodeError:
                    self._remove_output(destination)

            try:
                self._render_image_fallback(
                    destination,
                    duration,
                    caption_file,
                    cover,
                )
                return
            except NodeError as image_error:
                try:
                    self._render_svg_fallback(destination, duration, caption, cover)
                    return
                except NodeError as svg_error:
                    # Ultimate fallback: plain colour video so --no-h3 never hard-fails.
                    try:
                        self._render_color_fallback(destination, duration)
                        return
                    except NodeError as color_error:
                        raise color_error from svg_error
        except BaseException:
            self._remove_output(destination)
            raise
        finally:
            for path in auxiliary:
                self._remove_output(path)

    @staticmethod
    def _remove_output(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


__all__ = [
    "BuildBudget",
    "BudgetExceeded",
    "DEFAULT_BUDGET_CAP",
    "DEFAULT_BUILD_CAP",
    "DEFAULT_H3_CALL_COST",
    "H3_CALL_COST",
    "VideoNode",
    "_video_url",
]
