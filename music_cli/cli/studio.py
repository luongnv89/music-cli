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
@click.argument("brief", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--dist-dir",
    default=str(_trace.DEFAULT_DIST_DIR),
    show_default=True,
    help="Directory holding build projects.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Regenerate every audio node, ignoring the lock state.",
)
def studio_build(brief: Path, dist_dir: str, force: bool) -> None:
    """Run the audio-only build for the YAML BRIEF file."""
    try:
        parsed = load_brief_from_yaml(brief)
    except BuildError as exc:
        raise click.ClickException(str(exc)) from exc
    service = BuildService(dist_dir=dist_dir)
    try:
        result = service.run(parsed, force=force)
    except BuildError as exc:
        hint = f" Resume with `mc studio build {brief}`." if exc.stage != "plan" else ""
        raise click.ClickException(f"{exc}{hint}") from exc
    click.echo(
        f"build ok: project={result.project_dir.name} "
        f"plan={result.plan.get('plan_id')} "
        f"premiere={result.premiere_mp4 or result.premiere_wav}"
    )
