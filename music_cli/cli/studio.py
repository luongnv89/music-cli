"""`mc studio` — creative-compiler bookkeeping and audio-only build.

Read-only facades over :mod:`music_cli.studio.trace`:

- ``mc studio plan <project>`` — pretty-print ``dist/<project>/plan.yaml``
- ``mc studio trace <project>`` — render ``dist/<project>/trace.jsonl`` as a
  human-readable table

Build entry point (issue #139, task P3.3):

- ``mc studio build <brief.yaml>`` — run the audio-only build pipeline and
  write ``dist/<project>/premiere.mp4``.

The build itself is driven by :class:`music_cli.studio.build.BuildService`;
these commands let a user inspect the on-disk project layout afterwards.
"""

from __future__ import annotations

from pathlib import Path

import click

from ..studio import trace as _trace
from ..studio.build import BuildError, BuildService, load_brief_from_yaml
from ..studio.taste import from_playlist as _from_playlist
from ..studio.doctor import run_doctor
from ..studio.trace import DEFAULT_DIST_DIR
from .app import main
from .common import AliasedGroup


def _resolve_project(project: str, dist_dir: str) -> Path:
    """Resolve ``dist/<project>/`` or fail with a clear error."""
    proj = _trace.project_dir(dist_dir, project)
    if not proj.is_dir():
        raise click.ClickException(f"no build project '{project}' under {dist_dir}/")
    return proj


@main.group("studio", cls=AliasedGroup)
def studio_group() -> None:
    """Creative-compiler build pipeline (`mc studio`)."""


@studio_group.command("doctor")
@click.option(
    "--dist-dir",
    default=str(_trace.DEFAULT_DIST_DIR),
    show_default=True,
    help="Directory holding build projects.",
)
def studio_doctor(dist_dir: str) -> None:
    """Check dependencies and the output directory for an audio build."""
    results = run_doctor(dist_dir)
    for check in results:
        click.echo(f"{check.status}: {check.name}: {check.message}")
        if check.status != "OK" and check.fix:
            click.echo(f"  fix: {check.fix}", err=True)
    if any(check.status == "FAIL" for check in results):
        raise click.exceptions.Exit(1)


@studio_group.command("plan")
@click.argument("project")
@click.option(
    "--dist-dir",
    default=str(_trace.DEFAULT_DIST_DIR),
    show_default=True,
    help="Directory holding build projects.",
)
def studio_plan(project: str, dist_dir: str) -> None:
    """Pretty-print plan.yaml for PROJECT."""
    proj = _resolve_project(project, dist_dir)
    plan_file = proj / _trace.PLAN_FILENAME
    if not plan_file.exists():
        raise click.ClickException(
            f"no plan at {plan_file} (run a build before generating the project)"
        )
    click.echo(_trace.dump_plan_yaml(_trace.load_plan_yaml(plan_file)), nl=False)


@studio_group.command("trace")
@click.argument("project")
@click.option(
    "--dist-dir",
    default=str(_trace.DEFAULT_DIST_DIR),
    show_default=True,
    help="Directory holding build projects.",
)
def studio_trace(project: str, dist_dir: str) -> None:
    """Render the trace.jsonl decision log for PROJECT as a table."""
    proj = _resolve_project(project, dist_dir)
    trace_file = proj / _trace.TRACE_FILENAME
    if not trace_file.exists():
        raise click.ClickException(
            f"no trace at {trace_file} (run a build before inspecting the project)"
        )
    click.echo(_trace.render_trace_table(_trace.load_trace(trace_file)))


@studio_group.command("build")
@click.argument("brief", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--dist-dir",
    default=str(_trace.DEFAULT_DIST_DIR),
    show_default=True,
    help="Directory holding build projects.",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume from the persisted plan and completed audio nodes.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Regenerate every audio node, ignoring the lock state.",
)
@click.option(
    "--confirm",
    is_flag=True,
    default=False,
    help="Allow H3 scene generation to exceed the per-build budget cap.",
)
@click.option(
    "--no-h3",
    is_flag=True,
    default=False,
    help="Skip H3 and render captioned static scene visuals instead.",
)
@click.option(
    "--from-playlist",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a local playlist file (M3U/PLS). Extracts an abstract taste "
    "profile (tempo, key, loudness) to seed the Constitution. No artist or "
    "track names are included.",
)
def studio_build(
    brief: str,
    dist_dir: str,
    resume: bool,
    force: bool,
    confirm: bool,
    no_h3: bool,
    from_playlist: str | None,
) -> None:
    """Run the build for the YAML BRIEF file."""
    if resume and force:
        raise click.UsageError("--resume and --force cannot be used together")

    # Extract abstract taste profile from playlist if requested
    taste_profile: dict | None = None
    if from_playlist is not None:
        try:
            profile = _from_playlist(from_playlist)
            taste_profile = profile.to_dict()
            click.echo(
                f"taste profile: {profile.track_count} tracks, "
                f"loudness={profile.mean_loudness_db:.1f} dB, "
                f"dyn_range={profile.mean_dynamic_range_db:.1f} dB",
                err=True,
            )
        except OSError as exc:
            raise click.ClickException(str(exc)) from exc
        except Exception as exc:
            raise click.ClickException(f"failed to extract taste profile: {exc}") from exc

    try:
        parsed = load_brief_from_yaml(brief)
    except BuildError as exc:
        raise click.ClickException(str(exc)) from exc

    # Merge taste profile into the brief if provided
    if taste_profile is not None:
        parsed.taste = taste_profile

    service = BuildService(dist_dir=dist_dir)
    try:
        result = service.run(parsed, force=force, confirm=confirm, no_h3=no_h3)
    except BuildError as exc:
        hint = f" Resume with `mc studio build --resume {brief}`." if exc.stage != "plan" else ""
        raise click.ClickException(f"{exc}{hint}") from exc
    click.echo(
        f"build ok: project={result.project_dir.name} "
        f"plan={result.plan.get('plan_id')} "
        f"premiere={result.premiere_mp4 or result.premiere_wav}"
    )


@studio_group.command("revise")
@click.argument("project")
@click.argument("intent")
@click.option(
    "--dist-dir",
    default=str(DEFAULT_DIST_DIR),
    show_default=True,
    help="Directory holding build projects.",
)
def studio_revise(project: str, intent: str, dist_dir: str) -> None:
    """Revise PROJECT by regenerating only affected nodes.

    Calls the creative director to produce a plan-diff from INTENT, then
    re-runs only the nodes that must change.  Unaffected nodes stay locked
    and their on-disk artifacts are preserved.

    Example::

        mc studio revise my-project "Change the final scene to dawn"
    """
    service = BuildService(dist_dir=dist_dir)
    try:
        result = service.revise(project, intent)
    except BuildError as exc:
        hint = f" Check the plan at `mc studio plan {project}`."
        raise click.ClickException(f"{exc}{hint}") from exc
    changed = "regenerated" if result.regenerated else "no nodes changed"
    click.echo(
        f"revise ok: project={result.project_dir.name} "
        f"plan={result.plan.get('plan_id')} "
        f"premiere={result.premiere_mp4 or result.premiere_wav} "
        f"({changed})"
    )
