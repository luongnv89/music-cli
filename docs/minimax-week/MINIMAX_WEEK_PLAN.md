# MiniMax Week × GMI Cloud — Implementation Plan

**Project:** `music-cli`  
**Window:** 24 August – 6 September 2026  
**Track:** Multimodality  
**Baseline:** `pre-minimax-week` @ `1dbf3bb`

## Goal

Add a terminal-native creative compiler to `music-cli`. A text brief becomes an
M3-authored plan, generated audio, captions, and (when enabled) a composed
premiere. The build records decisions in `trace.jsonl`, persists its plan and
manifest, and supports partial rebuilds through locked nodes.

## Runtime decisions

- **H3:** `NO-GO`. The active video path is a static visual; live H3 calls are
  not required for the entry.
- **Audio:** Music 3.0 and Speech 2.8 HD use the GMI request queue. The live
  smoke check verified Music 3.0, while Speech 2.8 HD returned persistent
  provider-side `503` capacity errors.
- **Build mode:** audio-only is the default. `--no-h3` selects the static-visual
  path; `--confirm` is required for a paid H3 path when it is used later.
- **Validation:** use `.venv/bin/pytest -q -p no:cacheprovider`.

## Milestones

| Phase | Deliverable | Current state |
|---|---|---|
| Pre | Credentials, smoke checks, H3 decision | M3 and Music 3.0 verified; Speech blocked by capacity; H3 `NO-GO` recorded |
| P1 | Schemas, adapters, polling, cache, secrets | Implemented and covered by tests |
| P2 | M3 director and decision trace | Implemented; runtime plan prompts require non-empty fields plus `tracks`/`scenes` |
| P3 | Music/Speech nodes, mix, captions, `studio build` | Implemented and tested; live premiere remains blocked until Speech capacity is available |
| P4 | Static visuals and final assembly | Implemented and tested; no live H3 call required |
| P5 | Locking, graph, revise and partial rebuild | Implemented and covered by tests |
| P6 | Taste profile, doctor, install recipe, freeze | Implemented; final artifact checks remain pending |
| P7 | Demo recording and submission | Pending |

## Manual checks

```bash
mc cloud smoke --skip speech
mc studio doctor
mc studio build examples/neon-rain.yaml --force --no-h3
```

A successful live build must leave `dist/neon-rain/plan.yaml`,
`manifest.yaml`, `trace.jsonl`, generated nodes, captions, and
`premiere.mp4`. If the build stops at Speech 2.8 HD with `503`, preserve the
completed Music nodes and retry with `mc studio build --resume` after GMI
capacity recovers; do not claim a completed premiere from the partial output.

## Companion documents

- [`MINIMAX_WEEK_TASKS.md`](./MINIMAX_WEEK_TASKS.md) — issue-shaped task breakdown
- [`MINIMAX_WEEK_LOG.md`](./MINIMAX_WEEK_LOG.md) — measured API results and decisions
- [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md) — H3 decision record
- [`troubleshooting.md`](./troubleshooting.md) — validated failure modes and fixes
