"""music_cli.studio — creative compiler (MiniMax Week entry)."""

from .build import (
    Brief,
    BuildError,
    BuildResult,
    BuildService,
    default_adapter_factory,
    load_brief_from_yaml,
)
from .director import CritiqueReport, DirectorError, M3Director
from .doctor import (
    CheckResult,
    check_dist_dir,
    check_ffmpeg,
    check_ffprobe,
    check_gmi_key,
    run_doctor,
)
from .nodes.assemble import AssembleNode, AssembleNodeError
from .nodes.base import (
    BaseNode,
    NodeError,
    NodeLockedError,
    NodeProtocol,
)
from .nodes.ffmpeg import MixNode, MixNodeError, resolve_binary, write_srt
from .nodes.music import MusicNode
from .nodes.speech import SpeechNode
from .nodes.video import BudgetExceeded, BuildBudget, VideoNode
from .schemas import Constitution, CreativePlan, PlanDiff, ProjectManifest
from .trace import (
    DEFAULT_DIST_DIR,
    TraceWriter,
    dump_plan_yaml,
    init_project_layout,
    load_plan_yaml,
    load_trace,
    project_dir,
    project_paths,
    render_trace_table,
    write_plan_yaml,
)

__all__ = [
    "AssembleNode",
    "AssembleNodeError",
    "BaseNode",
    "BuildBudget",
    "BuildError",
    "BuildResult",
    "BuildService",
    "Brief",
    "BudgetExceeded",
    "CheckResult",
    "Constitution",
    "CreativePlan",
    "CritiqueReport",
    "DEFAULT_DIST_DIR",
    "check_dist_dir",
    "check_ffmpeg",
    "check_ffprobe",
    "check_gmi_key",
    "DirectorError",
    "M3Director",
    "MixNode",
    "MixNodeError",
    "MusicNode",
    "NodeError",
    "NodeLockedError",
    "NodeProtocol",
    "PlanDiff",
    "ProjectManifest",
    "default_adapter_factory",
    "load_brief_from_yaml",
    "resolve_binary",
    "run_doctor",
    "SpeechNode",
    "TraceWriter",
    "VideoNode",
    "dump_plan_yaml",
    "init_project_layout",
    "load_plan_yaml",
    "load_trace",
    "project_dir",
    "project_paths",
    "render_trace_table",
    "write_plan_yaml",
    "write_srt",
]
