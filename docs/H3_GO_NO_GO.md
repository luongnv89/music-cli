# DEFER — H3 Go / No-Go Decision (Day 4)

**Decision:** `DEFER` — decide Day 7. H3 requires a GMI key for real per-request calls; Pre.2 smoke harness has not yet run against live endpoints, so cost and latency are unknown.

## Rationale

- Pre.2 (`mc cloud smoke`, #152) is implemented but pending a GMI Cloud key. No live H3 call has been attempted; no cost/latency data exists to evaluate.
- H3 is a paid per-request model. Fabricating cost estimates would violate Day 4 honesty. Decision stays inside the Multimodality track regardless.
- Deferring to Day 7 is an allowed outcome per acceptance criteria.

## What flips to GO (Day 7 criteria)

Complete after one real H3 call via `mc cloud smoke` or a direct H3 request:

- **Estimated H3 cost per build:** `$__ / build` (from `dist/_smoke/summary.json` or provider billing; record model ID and endpoint)
- **Budget cap:** `$__ cap per __` (e.g. per day / per build batch); enforcement point (env var or config) to be documented
- **`--confirm` flag plan:** H3 generation is opt-in behind `--confirm` (or `--confirm-h3`). Without the flag the command must refuse to call H3 and print cost estimate + cap. With the flag it proceeds. Exact flag name and guard location to be filled Day 7.
- **Latency gate:** p50/p95 from the real call; if p95 exceeds the Day 7 threshold, treat as NO-GO.

If all three (cost, cap, flag) are recorded and within budget/latency, update this file's first line to `GO` and fill the values above.

## NO-GO fallback (degrade path)

Used when Day 7 decides `NO-GO` or when H3 is unavailable. P4 proceeds without H3; entry remains valid.

- **Output:** audio-only MP4, captioned, with a static visual — no H3 video generation.
- **Audio:** rendered track from Music 3.0 / Speech 2.8 (or local source), muxed as AAC.
- **Captions:** SRT/VTT burned in or muxed; source is the generated lyrics/transcript.
- **Visual:** single static image (H3 thumbnail or project cover) held for the audio duration.
- **ffmpeg (reference):**
  ```bash
  ffmpeg -loop 1 -i thumbnail.png -i audio.mp3 -i captions.srt \
    -c:v libx264 -tune stillimage -pix_fmt yuv420p \
    -c:a aac -shortest -vf "subtitles=captions.srt" out.mp4
  # If burn-in is not desired, mux captions as mov_text instead of -vf subtitles.
  ```
- **Premiere path:** the same MP4 (audio + captions + static visual) is the premiere artifact; no separate H3 step.

## Verification

```bash
test -f docs/H3_GO_NO_GO.md && head -1 docs/H3_GO_NO_GO.md | grep -E "GO|NO-GO|DEFER"
```

## References

- Pre.2: #152 — `mc cloud smoke` harness (`docs/MINIMAX_WEEK_LOG.md` Day 3)
- Source: `docs/MINIMAX_WEEK_TASKS.md` Pre.4
