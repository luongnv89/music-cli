# MiniMax Week Challenge Entry

**Repository:** [luongnv89/music-cli](https://github.com/luongnv89/music-cli)
**Compare:** [pre-minimax-week...main](https://github.com/luongnv89/music-cli/compare/pre-minimax-week...main)

## Scope

This entry packages the **MiniMax Week** work — a creative compilation pipeline built on top of music-cli's existing music-playing backbone. Since the `pre-minimax-week` tag, the project added a full `mc studio` creative compiler (director, graph builder, taste profiler, doctor), a GMI Cloud / MiniMax adapter layer with multi-provider support (GMI Cloud, OpenRouter), cloud secret management, and comprehensive test coverage. The entry is a terminal-native creative suite that turns text prompts into polished audio/video outputs, with decision logging via `trace.jsonl`.

## File Inventory

### Pre-existing files (shipped before MiniMax Week)

These files existed at the `pre-minimax-week` tag and ship as part of the entry unchanged:

| File |
|------|
| `.github/` |
| `.gitignore` |
| `.pre-commit-config.yaml` |
| `AGENTS.md` |
| `CHANGELOG.md` |
| `CLAUDE.md` |
| `CODE_OF_CONDUCT.md` |
| `CODE_REVIEW.md` |
| `CONTRIBUTING.md` |
| `LICENSE` |
| `MODERNIZATION_PLAN.md` |
| `MODERNIZATION_REPORT.md` |
| `README.md` |
| `SECURITY.md` |
| `assets/` |
| `constraints-dev.txt` |
| `docs/` |
| `install.sh` |
| `music-cli-ai.gif` |
| `music_cli/` |
| `original-prompt.png` |
| `pyproject.toml` |
| `scripts/` |
| `tests/` |

### Modified files (changed since pre-minimax-week)

| File | Change |
|------|--------|
| `CHANGELOG.md` | Updated with MiniMax Week entries |
| `README.md` | Updated with MiniMax Week section |
| `pyproject.toml` | Added `minimax` and `gmi` extras |

### New files (added since pre-minimax-week)

| File | Purpose |
|------|---------|
| `docs/H3_GO_NO_GO.md` | Go/no-go checklist for H3 milestone |
| `docs/MINIMAX_WEEK_LOG.md` | Development log for MiniMax Week |
| `docs/MINIMAX_WEEK_TASKS.md` | Task breakdown for MiniMax Week |
| `examples/neon-rain.yaml` | Example studio build definition |
| `music_cli/cli/cloud.py` | Cloud command group (GMI / OpenRouter) |
| `music_cli/cli/cloud_smoke.py` | Cloud smoke-test command |
| `music_cli/cli/studio.py` | Studio command group (build, doctor, taste) |
| `music_cli/cloud/__init__.py` | Cloud adapter base |
| `music_cli/cloud/base.py` | Base cloud provider interface |
| `music_cli/cloud/gmi.py` | GMI Cloud adapter |
| `music_cli/cloud/openrouter.py` | OpenRouter adapter |
| `music_cli/cloud/secrets.py` | Cloud secret management |
| `music_cli/cloud/strategy_cache.py` | Provider strategy caching |
| `music_cli/studio/__init__.py` | Studio package init |
| `music_cli/studio/build.py` | Build orchestration |
| `music_cli/studio/director.py` | Studio director (workflow engine) |
| `music_cli/studio/doctor.py` | Health check / doctor command |
| `music_cli/studio/graph.py` | DAG graph builder |
| `music_cli/studio/nodes/__init__.py` | Nodes package init |
| `music_cli/studio/nodes/assemble.py` | Assemble node |
| `music_cli/studio/nodes/base.py` | Base node class |
| `music_cli/studio/nodes/ffmpeg.py` | FFmpeg processing node |
| `music_cli/studio/nodes/music.py` | Music generation node |
| `music_cli/studio/nodes/speech.py` | Speech synthesis node |
| `music_cli/studio/nodes/video.py` | Video composition node |
| `music_cli/studio/schemas.py` | Build schema definitions |
| `music_cli/studio/taste.py` | Taste profiler |
| `music_cli/studio/trace.py` | Decision trace logger |
| `tests/fixtures/gmi_recorded.json` | Recorded GMI Cloud fixture |
| `tests/fixtures/openrouter_recorded.json` | Recorded OpenRouter fixture |
| `tests/test_cli_cloud.py` | Cloud CLI tests |
| `tests/test_cloud.py` | Cloud adapter tests |
| `tests/test_cloud_gmi.py` | GMI adapter tests |
| `tests/test_cloud_openrouter.py` | OpenRouter adapter tests |
| `tests/test_cloud_smoke.py` | Cloud smoke tests |
| `tests/test_studio_assemble.py` | Assemble node tests |
| `tests/test_studio_build.py` | Build tests |
| `tests/test_studio_director.py` | Director tests |
| `tests/test_studio_doctor.py` | Doctor tests |
| `tests/test_studio_ffmpeg.py` | FFmpeg node tests |
| `tests/test_studio_graph.py` | Graph tests |
| `tests/test_studio_nodes.py` | Node tests |
| `tests/test_studio_revise.py` | Revise tests |
| `tests/test_studio_schemas.py` | Schema tests |
| `tests/test_studio_taste.py` | Taste tests |
| `tests/test_studio_trace.py` | Trace tests |
| `tests/test_studio_video_node.py` | Video node tests |
