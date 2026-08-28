"""`mc studio` — creative-compiler bookkeeping (issue #136, task P2.2).

Read-only facades over :mod:`music_cli.studio.trace`:

- ``mc studio plan <project>`` — pretty-print ``dist/<project>/plan.yaml``
- ``mc studio trace <project>`` — render ``dist/<project>/trace.jsonl`` as a
  human-readable table

The build itself is driven by :class:`music_cli.studio.director.M3Director`;
these commands let a user inspect the on-disk project layout afterwards.
"""

from __future__ import annotations

from pathlib import Path

import click

from ..studio import trace as _trace
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
    """Inspect creative-compiler build projects (`mc studio`)."""


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
