# MiniMax Week Log

Working log for MiniMax Week x GMI Cloud de-risking. Each day records what was
built, what was measured with real API calls, and any pivot decisions.

## Day 3 — Pre.2: Smoke-test M3, Music 3.0, Speech 2.8 (#152)

Date: _pending first real run_

### Status

- [x] Harness shipped: `mc cloud smoke` fires one real call per free model,
      writes `dist/_smoke/{m3_response.txt,music.mp3,speech.mp3,summary.json}`,
      and records timestamp/latency/size/format per check.
- [ ] Real M3 call (< 30 s text response)
- [ ] Real Music 3.0 call (audio in documented format)
- [ ] Real Speech 2.8 call (audio in documented format)
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
| m3 | `MiniMax-M3` | `POST https://api.gmi-serving.com/v1/chat/completions` | text |
| music | `minimax-music-3.0` | `POST https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests` (+ poll) | mp3 |
| speech | `minimax-tts-speech-2.8-hd` | same request queue (+ poll) | mp3 |

### Results

Fill one row per real call from `dist/_smoke/summary.json`:

| Check | Timestamp (UTC) | Latency (s) | Size (bytes) | Format | Status |
|-------|-----------------|-------------|--------------|--------|--------|
| m3    | —               | —           | —            | —      | pending |
| music | —               | —           | —            | —      | pending |
| speech| —               | —           | —            | —      | pending |
| h3    | —               | —           | —            | —      | not attempted |

### Notes / pivots

- No GMI Cloud account/key existed at implementation time, so the harness was
  built against the documented GMI endpoints and verified with mocked HTTP in
  the test suite (`tests/test_cloud_smoke.py`). The three real calls above are
  the remaining manual step once an account exists.
- If any model turns out unreachable or unusable on first run, record the
  failure row verbatim from `summary.json` here and pivot to whatever is
  reachable.
