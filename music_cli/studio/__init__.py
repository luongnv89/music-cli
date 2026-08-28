"""music_cli.studio — creative compiler (MiniMax Week entry)."""

from .build import (
    Brief,
    BuildError,
    BuildResult,
    BuildService,
    default_adapter_factory,
    load_brief_from_yaml,
)
from .director import CritiqueReport
from .doctor import (
    CheckResult,
    check_disk_space,
    check_h3_budget,
    check_network,
    check_openrouter_key,
    check_disk_space,
    check_h3_budget,
    check_network,
    check_openrouter_key,
    run_doctor,
)
from .graph import (
    GraphCycleError,
    GraphError,
    GraphMissingDependencyError,
    Node,
    ProjectGraph,
)
from .nodes.assemble import AssembleNode, AssembleNodeError
from .nodes.base import (
    BaseNode,
    NodeError,  # noqa: F401 - re-exported
    NodeLockedError,  # noqa: F401 - re-exported
    NodeProtocol,
)
from .nodes.ffmpeg import (  # noqa: F401 - re-exported
    MixNode,
    MixNodeError,
    resolve_binary,
    write_srt,
)
from .nodes.music import MusicNode  # noqa: F401 - re-exported
from .nodes.speech import SpeechNode
from .nodes.video import BudgetExceeded, BuildBudget, VideoNode
from .schemas import Constitution, CreativePlan, PlanDiff, ProjectManifest
from .taste import FFProbeError, TasteProfile, from_playlist
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
    "FFProbeError",
    "GraphCycleError",
    "GraphError",
    "GraphMissingDependencyError",
    "Node",
    "NodeLockedError",
    "NodeProtocol",
    "PlanDiff",
    "ProjectGraph",
    "ProjectManifest",
    "TasteProfile",
    "default_adapter_factory",
    "from_playlist",
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
