"""Command-line interface for music-cli.

The CLI is split one module per command group (F-CLEAN-007). This package
root assembles the shared ``main`` group, registers the hidden aliases, and
re-exports the historical names so ``music_cli.cli`` keeps resolving exactly
as it did when everything lived in a single module.
"""

from .. import __github_url__, __version__  # noqa: F401  (historical re-exports)
from .ai import ai_group, ai_list, ai_models_group, ai_play, ai_remove, ai_replay
from .ai_models import (
    ai_models_delete,
    ai_models_download,
    ai_models_list,
    ai_models_set_default,
)
from .app import _check_for_updates_once, main
from .cloud import KEYRING_SERVICE, cloud_group, key_delete, key_get, key_list, key_set
from .common import (
    _ICON_FALLBACKS,
    INSPIRATIONAL_QUOTES,
    AliasedGroup,
    _is_no_color,
    _register_alias,
    get_random_quote,
    icon,
)
from .daemon_cmds import _terminate_daemon, daemon_control
from .history import history_group, history_list, history_play
from .misc import list_moods, show_config
from .playback import (
    PlayOptions,
    _detect_mode_and_source,
    _detect_play_mode,
    _render_play_response,
    _require_ffplay,
    _resolve_local_path,
    _run_play,
    _warn_deprecated_modes,
    next_track,
    pause,
    play,
    resume,
    status,
    stop,
    volume,
)
from .radio import (
    radio_update,
    radios_add,
    radios_group,
    radios_list,
    radios_play,
    radios_remove,
    update_radios_legacy,
)
from .runtime import (
    ComposingAnimation,
    _daemon_log_path,
    ensure_daemon,
    start_daemon_background,
)
from .youtube import youtube_cached, youtube_clear, youtube_group, youtube_play, youtube_remove

__all__ = [
    "INSPIRATIONAL_QUOTES",
    "KEYRING_SERVICE",
    "AliasedGroup",
    "ComposingAnimation",
    "PlayOptions",
    "__github_url__",
    "__version__",
    "_ICON_FALLBACKS",
    "_check_for_updates_once",
    "_daemon_log_path",
    "_detect_mode_and_source",
    "_detect_play_mode",
    "_is_no_color",
    "_register_alias",
    "_render_play_response",
    "_resolve_local_path",
    "_require_ffplay",
    "_run_play",
    "_terminate_daemon",
    "_warn_deprecated_modes",
    "ai_group",
    "ai_list",
    "ai_models_delete",
    "ai_models_download",
    "ai_models_group",
    "ai_models_list",
    "ai_models_set_default",
    "ai_play",
    "ai_remove",
    "ai_replay",
    "cloud_group",
    "daemon_control",
    "ensure_daemon",
    "get_random_quote",
    "history_group",
    "history_list",
    "history_play",
    "icon",
    "key_delete",
    "key_get",
    "key_list",
    "key_set",
    "list_moods",
    "main",
    "next_track",
    "pause",
    "play",
    "radio_update",
    "radios_add",
    "radios_group",
    "radios_list",
    "radios_play",
    "radios_remove",
    "resume",
    "show_config",
    "start_daemon_background",
    "status",
    "stop",
    "update_radios_legacy",
    "volume",
    "youtube_cached",
    "youtube_clear",
    "youtube_group",
    "youtube_play",
    "youtube_remove",
]

# ---------------------------------------------------------------------------
# Register aliases (hidden — don't appear in --help but work on the CLI)
# ---------------------------------------------------------------------------

# Task 1.3: Old group/command names -> hidden aliases on main
_register_alias(main, "radios", "radio")
_register_alias(main, "youtube", "yt")
_register_alias(main, "moods", "mood")
_register_alias(main, "volume", "vol")

# Task 1.4: Playback single-letter/short aliases
_register_alias(main, "s", "stop")
_register_alias(main, "pp", "pause")
_register_alias(main, "r", "resume")
_register_alias(main, "n", "next")
_register_alias(main, "st", "status")
_register_alias(main, "h", "history")

# Task 1.3: Inside yt group, "cached" -> "list"
_register_alias(youtube_group, "cached", "list")

# Task 2.6: "models" -> "model" (old name), "set-default" -> "default" (old name)
_register_alias(ai_group, "models", "model")
_register_alias(ai_models_group, "set-default", "default")

if __name__ == "__main__":
    main()
