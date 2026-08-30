# MiniMax Week Log

Working log for MiniMax Week x GMI Cloud de-risking. Each day records what was
built, what was measured with real API calls, and any pivot decisions.

## Day 3 — Pre.2: Smoke-test M3, Music 3.0, Speech 2.8 (#152)

Date: 2026-08-29

### Status

- [x] Harness shipped: `mc cloud smoke` fires one real call per free model,
      writes `dist/_smoke/{m3_response.txt,music.mp3,speech.mp3,summary.json}`,
      and records timestamp/latency/size/format per check.
- [x] Real M3 call — OK in 1.8s (text response)
- [x] Real Music 3.0 call — OK in 80.4s (1.8MB mp3)
- [ ] Real Speech 2.8 call — model exists but persistently 503 (capacity exhausted)
- [ ] One H3 call attempted if budget allows; H3 cost recorded

### How to run

```bash
pip install 'coder-music-cli[gmi]'
mc cloud key set gmi        # paste the GMI Cloud key once
mc cloud smoke              # writes dist/_smoke/ + summary.json
```

Endpoints used by the harness:

| Check | Model ID | Endpoint | Output format |
|-------|----------|----------|---------------|
| m3    | `MiniMaxAI/MiniMax-M3` | `POST https://api.gmi-serving.com/v1/chat/completions` | text |
| music | `minimax-music-3.0` | `POST https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests` (+ poll) | mp3 |
| speech| `minimax-tts-speech-2.8-hd` | same request queue (+ poll) | mp3 |

> **Note:** M3 model name corrected from `MiniMax-M3` to `MiniMaxAI/MiniMax-M3`
> in smoke harness (#178) — the serving endpoint requires the full namespace.

### Results

| Check | Timestamp (UTC) | Latency (s) | Size (bytes) | Format | Status |
|-------|-----------------|-------------|--------------|--------|--------|
| m3    | 2026-08-29T21:10:45 | 1.844 | 8 | text | ✅ OK |
| music | 2026-08-29T21:12:06 | 80.401 | 1783473 | mp3 | ✅ OK |
| speech| 2026-08-29T21:12:07 | 0.865 | — | — | ⚠️ 503 (capacity) |
| h3    | —               | —           | —            | —      | not attempted |

### Notes / pivots

- **M3**: Endpoint `api.gmi-serving.com` works. Model name must be `MiniMaxAI/MiniMax-M3`
  (not `MiniMax-M3`) — the serving endpoint requires the full namespace prefix.
- **Music 3.0**: Fully functional. ~80s latency for a short track, 1.8MB mp3 output.
- **Speech 2.8 HD**: Model `minimax-tts-speech-2.8-hd` exists on the queue endpoint
  but returns persistent 503 "Upstream capacity temporarily exhausted" across
  multiple attempts over 30+ minutes. This is a GMI Cloud capacity issue, not a
  code issue. Non-HD variants (`minimax-tts-speech-2.8`, `minimax-speech-2.8`, etc.)
  all return 404 "model does not exist" — only the `-hd` variant exists.
- **H3**: Not attempted — requires a separate GMI key scope for H3 model access.
- If Speech 2.8 capacity recovers, retry with `mc cloud smoke` (or skip with
  `mc cloud smoke --skip speech` to test the other two independently).

## Day 3 — Pre.3: Confirm pre-existing-repo eligibility with organizers (#153)

Date: 2026-08-26

### Status

**Pending** — question not yet sent; awaiting organizer reply.

- [ ] Question sent through the documented channel (campaign form or contact email)
- [ ] Reply received and pasted into this log
- [x] Fallback defined if rejected (below)

### Question to send

> Is a pre-existing public repo allowed if the GMI/MiniMax integration, the
> `studio` command group, and the audiovisual pipeline are built during the
> 14-day window?

Send via the campaign form or the organizers' contact email (whichever channel
the campaign documents). Paste the verbatim reply under **Reply** below.

### Reply

_pending_

### Fallback if rejected

Relocate all `feat/minimax-week-studio` work to a fresh repository before the
window opens.

## Integration follow-up — live build retry

Date: 2026-08-30

The first live build exposed adapter/runtime mismatches that recorded fixtures
did not cover:

- M3's caller-supplied system prompt was being discarded by `GMIAdapter`, so
  the model could return a schema-valid plan without runtime `tracks`/`scenes`.
- GMI queue jobs finish with status `success`, and live media is nested under
  `outcome`; the adapter now accepts both queue terminal statuses and unwraps
  both response shapes.
- The queue requires UUIDv4-form idempotency headers; the deterministic
  internal request key is converted at the GMI boundary. Music/Speech payloads
  now use the audio settings from the successful smoke request.
- A real resumed build generated and probed five Music 3.0 tracks. It stopped
  at Speech 2.8 HD with the provider's persistent `HTTP 503` capacity error.
  The completed Music files remain in `dist/neon-rain/nodes/` and are reused by
  `mc studio build --resume`.

No verified `premiere.mp4` exists until Speech capacity recovers. H3 remains
`NO-GO`; the next live retry should use `--resume --no-h3`.
