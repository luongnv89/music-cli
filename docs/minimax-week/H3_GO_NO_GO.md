# NO-GO — H3 Decision (Day 4)

**Decision:** `NO-GO` — degrade to audio-only + static visual. No H3 video generation.

## Rationale

- H3 access is not verified for the current GMI account; no live H3 call has been attempted, so no cost or latency data exists.
- Speech 2.8 HD exists but is persistently at capacity (`503`) across multiple attempts, so the live audio/video path already has an external capacity risk.
- H3 is a paid per-request model. Without verified cost/latency data, proceeding would be a risk.
- The entry remains valid inside the Multimodality track with the audio-only + static visual fallback.

## GO criteria (never met)

These criteria were defined for Day 7 but are not applicable since we chose NO-GO:

- **Estimated H3 cost per build:** unknown (no H3 key, no calls attempted)
- **Budget cap:** unknown
- **`--confirm` flag:** implemented in code (`--no-h3` flag exists and works)
- **Latency gate:** unknown

## NO-GO fallback (active path)

P4 proceeds without H3; the entry remains valid.

- **Output:** audio-only MP4, captioned, with a static visual — no H3 video generation.
- **Audio:** rendered track from Music 3.0 / Speech 2.8 (or local source), muxed as AAC.
- **Captions:** SRT/VTT burned in or muxed; source is the generated lyrics/transcript.
- **Visual:** single static image (project cover or generated via ffmpeg drawtext) held for the audio duration.
- **ffmpeg (reference):**
  ```bash
  ffmpeg -loop 1 -i thumbnail.png -i audio.mp3 -i captions.srt \
    -c:v libx264 -tune stillimage -pix_fmt yuv420p \
    -c:a aac -shortest -vf "subtitles=captions.srt" out.mp4
  # If burn-in is not desired, mux captions as mov_text instead of -vf subtitles.
  ```
- **Premiere path:** the same MP4 (audio + captions + static visual) is the premiere artifact; no separate H3 step.

## Code impact

The `--no-h3` flag and `--confirm` guard are already implemented in the codebase:

- `VideoNode` falls back to static visual from `cover_art` or ffmpeg drawtext when `--no-h3` is passed
- Budget guard raises `BudgetExceeded` when projected cost exceeds the cap without `--confirm`
- No live H3 calls are required in CI

## Verification

```bash
test -f docs/minimax-week/H3_GO_NO_GO.md && head -1 docs/minimax-week/H3_GO_NO_GO.md | grep -E "NO-GO"
```

## References

- Pre.2: #152 — `mc cloud smoke` harness ([`MINIMAX_WEEK_LOG.md`](./MINIMAX_WEEK_LOG.md) Day 3)
- Source: [`MINIMAX_WEEK_TASKS.md`](./MINIMAX_WEEK_TASKS.md) Pre.4
