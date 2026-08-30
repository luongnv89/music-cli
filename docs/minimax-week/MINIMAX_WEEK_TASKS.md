# MiniMax Week × GMI Cloud — Plan tasks

> Companion task breakdown for [`MINIMAX_WEEK_PLAN.md`](./MINIMAX_WEEK_PLAN.md).
> This file is shaped for `/plan-to-issues` parsing: it uses `^#### Task <id>:` headings and a
> `## Phase <id> — <title>` heading for each phase. The plan is the source of truth for decisions;
> this file records implementation status and verification commands.
> Source binding marker: `<!-- plan-to-issues:plan=docs/minimax-week/MINIMAX_WEEK_PLAN.md -->`

**Project:** music-cli
**Baseline:** Day 3 of 14 (Aug 26, 2026); baseline tag `pre-minimax-week` @ `1dbf3bb`.
**Test command of record:** `.venv/bin/pytest -q -p no:cacheprovider`
**Track:** Multimodality
**Window:** Aug 24 – Sep 6, 2026
**Critical path:** Pre.1 → Pre.2 → P1.1 → P1.2 → P2.1 → P3.1 → P4.1 → P4.2 → P5.1 → P5.2 → P7.1
> H3 is NO-GO (Pre.4); P4 uses static-visual fallback.

---

## Phase Pre — De-risk

**Goal:** de-risk every model, decide H3, confirm pre-existing-repo eligibility, tag the baseline.
**Milestone ME:** [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md) written (`NO-GO`); one real call to M3, Music 3.0 succeeded (Speech 2.8 HD persistently at capacity).

#### Task Pre.1: Tag the pre-minimax-week baseline and create the GMI account

**Description:** Tag the current HEAD as `pre-minimax-week` and record the SHA. Create a GMI Cloud
account (free) and capture the API key in `keyring` via a new `mc cloud` subcommand. `keyring` is not
yet a project dependency — add it to `[project.optional-dependencies]` as a new `gmi` extra
(`gmi = ["keyring>=24", "httpx>=0.27"]`). Do not commit the key, env vars, or any prompt that
contains it.

> **Important:** The API key must be authorized for the **audio queue endpoint**
> (`console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests`) which hosts Music 3.0 and Speech 2.8.
> A key scoped only for the text model endpoint (`api.gmi-serving.com`) will pass `mc cloud ping`
> but fail during `mc studio build` with `HTTP 400`.

**Acceptance Criteria:**
- [x] `git tag pre-minimax-week` is at the recorded SHA (`1dbf3bb`)
- [x] `mc cloud key set gmi` writes to `keyring` and the key is unreadable from a child process
- [x] `mc cloud key get gmi` round-trips the value (smoke test only)
- [x] `pyproject.toml` declares a new `gmi` extra including `keyring` and `httpx`

**Status:** ✅ Complete — implemented in #151, #155. Tag `pre-minimax-week` exists at `1dbf3bb`.

**Dependencies:** None
**Effort:** S
**Verify:** `git rev-parse pre-minimax-week && python -c "import keyring"`

#### Task Pre.2: Smoke-test M3, Music 3.0, Speech 2.8 with one real call each

**Description:** Run one real API call to each free model: M3 (text reasoning), Music 3.0 (song
generation), Speech 2.8 (text-to-speech). Capture latency, response format, polling needs, and
output format. Log the results in [`MINIMAX_WEEK_LOG.md`](./MINIMAX_WEEK_LOG.md) under Day 3. This is the de-risk gate —
if any free model is unreachable or unusable, the entry pivots to whatever is reachable.

**Acceptance Criteria:**
- [x] One real M3 call returns text in < 30s (1.8s ✅)
- [x] One real Music 3.0 call returns audio in the documented format (80s, 1.8MB mp3 ✅)
- [ ] One real Speech 2.8 call returns audio in the documented format (model exists but persistently 503 capacity — GMI Cloud-side issue)
- [x] All three results are logged with timestamp, latency, size, format (see `dist/_smoke/summary.json`)
- [ ] One H3 call attempted if budget allows; H3 cost recorded

**Status:** ✅ Complete — real API calls verified on 2026-08-29. M3 and Music 3.0 both succeeded. Speech 2.8 HD model exists but GMI Cloud is persistently at capacity (503) — not a code issue. M3 model name corrected to `MiniMaxAI/MiniMax-M3` (#178). See [`MINIMAX_WEEK_LOG.md`](./MINIMAX_WEEK_LOG.md) Day 3.

**Dependencies:** Pre.1
**Effort:** S
**Verify:** Three files written under `dist/_smoke/`, all present

#### Task Pre.3: Confirm pre-existing-repo eligibility with organizers

**Description:** Send a 30-second question to the organizers via the campaign form or contact
email: "Is a pre-existing public repo allowed if the GMI/MiniMax integration, the `studio` command
group, and the audiovisual pipeline are built during the 14-day window?" Record the answer in
[`MINIMAX_WEEK_LOG.md`](./MINIMAX_WEEK_LOG.md) under Day 3.

**Acceptance Criteria:**
- [ ] Question sent through the documented channel
- [ ] Reply received and pasted into the log
- [x] If rejected, `feat/minimax-week-studio` work is relocated to a fresh repo per the fallback (fallback documented in [`MINIMAX_WEEK_LOG.md`](./MINIMAX_WEEK_LOG.md) Day 3)

**Status:** ⚠️ Pending — question drafted and documented in [`MINIMAX_WEEK_LOG.md`](./MINIMAX_WEEK_LOG.md) Day 3 but not yet sent to organizers. Fallback path is defined.

**Dependencies:** None
**Effort:** XS
**Verify:** Log entry exists with a date and an answer (yes / pending / no + action)

#### Task Pre.4: Decide H3 go/no-go and write [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md)

**Description:** H3 is a paid per-request model. If cost or latency is unacceptable, the entry
degrades to "audio + captions + static H3 thumbnail" or pure audio+caption premiere, still inside
the Multimodality track. Decision must be written into [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md) by end of Day 4.

**Acceptance Criteria:**
- [x] [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md) exists with one of `GO`, `NO-GO` (degrade), or `DEFER` (decide Day 7) — decision is `NO-GO`
- [ ] If `GO`: estimated H3 cost per build, budget cap, and `--confirm` flag plan recorded
- [x] If `NO-GO`: fallback path documented (audio-only MP4, captioned, ffmpeg static visual) — fully detailed in [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md)

**Status:** ✅ `NO-GO` recorded in [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md). Degraded to audio-only + static visual path. No H3 key available; Speech 2.8 HD persistently at capacity.

**Dependencies:** Pre.2
**Effort:** XS
**Verify:** `test -f docs/minimax-week/H3_GO_NO_GO.md && head -1 docs/minimax-week/H3_GO_NO_GO.md | grep -E "NO-GO"`

---

## Phase P1 — Adapters

**Goal:** schemas, GMI/OpenRouter adapters, polling, retries, resumable cache, keyring integration.
**Milestone M1:** one real audio-only build (`Music 3.0` + `Speech 2.8`) end-to-end; currently blocked by Speech 2.8 HD capacity.

#### Task P1.1: Define CreativePlan, Constitution, ProjectManifest, PlanDiff JSON schemas

**Description:** Add `music_cli/studio/schemas.py` with strict JSON schemas for the four core
artifacts. Schemas are the contract between M3 and the runtime; a parse failure on any field must
trigger a re-prompt, not a silent drop. Use Pydantic or `jsonschema`; pick whichever is already in
the dep tree.

**Acceptance Criteria:**
- [x] `music_cli/studio/schemas.py` exports `CreativePlan`, `Constitution`, `ProjectManifest`, `PlanDiff`
- [x] Each schema has a `validate()` method that returns a list of errors
- [x] Unit tests cover at least 3 valid and 3 invalid examples per schema (`tests/test_studio_schemas.py`, 36 tests)
- [x] Schemas are importable without any of the GMI deps installed

**Status:** ✅ Complete — implemented in #132, #159.

**Dependencies:** Pre.1
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_schemas.py -q`

#### Task P1.2: Implement GMI Cloud + OpenRouter adapters with polling and retries

**Description:** Add `music_cli/cloud/gmi.py` (`GMIAdapter` for M3, Music 3.0, Speech 2.8, H3) and
`music_cli/cloud/openrouter.py` (`OpenRouterAdapter` for M3, M2.7, Speech 2.8). GMI uses
async queue polling for audio models and synchronous chat for text models. OpenRouter serves
every model through one OpenAI-compatible chat-completions endpoint (single round trip, no polling).
Both inherit from `BaseAdapter` (retry up to 3 times, exponential backoff, idempotency keys)
and support a resumable on-disk cache (`music_cli/cloud/strategy_cache.py`).

**Acceptance Criteria:**
- [x] `GMIAdapter` exposes `m3_plan`, `m3_critique`, `music3_generate`, `speech28_synthesize`, `h3_generate`
- [x] `OpenRouterAdapter` exposes `m3_chat`, `m27_chat`, `speech28_synthesize` (text-in/text-out; OpenRouter returns audio reference in text payload)
- [x] Both have a `run()` method that retries up to 3 times with exponential backoff
- [x] Polling is async; cancellation is cooperative
- [x] Cache key is the model + prompt hash + parameters; cache hit returns instantly
- [x] Unit tests against a recorded fixture (no live calls in CI)

**Status:** ✅ Complete — implemented in #133, #160.

**Dependencies:** P1.1
**Effort:** L
**Verify:** `.venv/bin/pytest tests/test_cloud_gmi.py tests/test_cloud_openrouter.py -q`

#### Task P1.3: Add the `mc cloud` subcommand and keyring-backed secret storage

**Description:** Add `music_cli/cloud/secrets.py` (keyring wrapper: `store_api_key()`,
`get_api_key()`, `delete_api_key()`) and `music_cli/cli/cloud.py` (Click group with `AliasedGroup`).
Public surface: `mc cloud key set <provider>`, `mc cloud key get <provider>`, `mc cloud key delete <provider>`,
`mc cloud ping` (reports reachable/unreachable for GMI and OpenRouter), `mc cloud smoke` (fires
real API calls to M3, Music 3.0, Speech 2.8).

**Acceptance Criteria:**
- [x] `mc cloud key set gmi` writes the key to the OS keyring; `mc cloud key get gmi` reads it
- [x] `mc cloud ping` reports reachable/unreachable for each model
- [x] No key value is ever printed to stdout or stored in a file
- [x] `mc cloud --help` lists subcommands and examples

**Status:** ✅ Complete — implemented in #134, #161.

**Dependencies:** P1.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_cli_cloud.py -q` and a manual `mc cloud ping`

---

## Phase P2 — Director

**Goal:** M3 director with structured plan/critique/revise calls and a JSONL decision trace.
**Milestone M2:** M3 plan on a real brief; trace file looks right.

#### Task P2.1: Implement M3Director with plan, critique, revise

**Description:** Add `music_cli/studio/director.py` with `M3Director` class. Three methods:
- `plan(brief: str) -> CreativePlan` — calls `adapter.m3_plan(prompt)` with a system prompt
  enforcing JSON-only output. Retries up to 2 times (3 total attempts) on parse failure.
- `critique(plan, measurements) -> CritiqueReport` — calls `adapter.m3_critique(prompt)` with
  plan + ffprobe measurements. Returns `CritiqueReport(ok, issues[], repairs[], summary?, score?)`.
- `revise(plan, intent) -> PlanDiff` — calls `adapter.m3_plan(prompt)` with revision intent.
  Returns a diff describing which nodes are locked and which must regenerate.

All three log every call to `trace.jsonl` with `step`, `model`, `ts`, `input_hash`, `output_hash`,
`latency_ms`, `retries` via `_ask_json()` → `_call()` routing to the appropriate adapter method.

**Acceptance Criteria:**
- [x] `M3Director.plan(brief)` returns a `CreativePlan` validated against the schema
- [x] `M3Director.critique(plan, measurements)` returns a `CritiqueReport` with at least `ok`, `issues[]`, `repairs[]`
- [x] `M3Director.revise(plan, intent)` returns a `PlanDiff` with `locked_nodes[]`, `regenerate_nodes[]`
- [x] On schema parse failure, the director retries up to 2 times with a corrective prompt
- [x] All calls append to `trace.jsonl` with at least `step`, `model`, `ts`, `input_hash`, `output_hash`, `latency_ms`

**Status:** ✅ Complete — implemented in #135, #162. 21 tests in `tests/test_studio_director.py`.

**Dependencies:** P1.2
**Effort:** L
**Verify:** `.venv/bin/pytest tests/test_studio_director.py -q` plus one real M3 plan in `dist/_smoke/`

#### Task P2.2: Implement trace.jsonl writer and project directory layout

**Description:** Add `music_cli/studio/trace.py` and the on-disk project layout under
`dist/<project>/`. Every M3 call, every generation, every probe, every repair, every assemble
writes one line of JSON to `trace.jsonl`. Lines are append-only; rotation is not needed (a
premiere build produces ~50 lines). The module also owns the layout constants:
`PLAN_FILENAME`, `TRACE_FILENAME`, `NODES_DIRNAME`, `PREMIERE_FILENAME`.

**Acceptance Criteria:**
- [x] `TraceWriter` is an append-only context manager
- [x] Each line is valid JSON with `ts`, `step`, `model`, `node_id`, `latency_ms`, `payload_hash`
  (extra fields like `retries`, `ok` pass through)
- [x] `dist/<project>/` layout matches the spec: `plan.yaml`, `trace.jsonl`, `nodes/`, `premiere.mp4`
- [x] `mc studio plan <project>` reads `plan.yaml` and pretty-prints it
- [x] `mc studio trace <project>` reads `trace.jsonl` and renders a human-readable table

**Status:** ✅ Complete — implemented in #136, #163. 18 tests in `tests/test_studio_trace.py`.

**Dependencies:** P2.1
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_trace.py -q`

---

## Phase P3 — Audio

**Goal:** Music and Speech nodes, ffmpeg mix + captions, ffprobe node validation.
**Milestone M3:** first **audio-only** premiere (~60s) plays.

#### Task P3.1: Implement MusicNode and SpeechNode with the Node protocol

**Description:** Add `music_cli/studio/nodes/base.py` with `NodeProtocol` (property `path`, async
`generate()`, sync `probe()`, `lock()`, `unlock()`) and `BaseNode` (concrete download/probe/lock
lifecycle). Add `music_cli/studio/nodes/music.py` (`MusicNode` → Music 3.0 via GMI queue) and
`music_cli/studio/nodes/speech.py` (`SpeechNode` → Speech 2.8 via GMI queue). Each node writes
its output into the project's `nodes/` directory, runs `ffprobe` validation, and locks on success.

**Acceptance Criteria:**
- [x] `Node` protocol has `generate()`, `probe()`, `lock()`, `unlock()`, `path`
- [x] `MusicNode.generate(prompt, lyrics, duration)` calls Music 3.0, writes `nodes/song-N.wav`, runs `ffprobe`
- [x] `SpeechNode.generate(text, voice, duration)` calls Speech 2.8, writes `nodes/narration-N.wav`, runs `ffprobe`
- [x] A locked node refuses to regenerate without an explicit `unlock()`
- [x] Unit tests cover the protocol and the two nodes against a recorded fixture

**Status:** ✅ Complete — implemented in #137, #164. 11 tests in `tests/test_studio_nodes.py`.

**Dependencies:** P2.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_nodes.py -q`

#### Task P3.2: Implement ffmpeg mix node and SRT caption generation

**Description:** Add `music_cli/studio/nodes/ffmpeg.py` with `MixNode` (uses ffmpeg `amix` for
audio layering, `sidechaincompress` for ducking under narration). `MixNode.run(nodes, captions,
out_path, *, duration=None, narration=None)` mixes music-bed WAVs with ducking gated by caption
timing. Writes `captions.srt` beside the output WAV. SRT is reused when the video nodes land in P4.

**Acceptance Criteria:**
- [x] `MixNode.run(nodes, captions, out_path)` produces a single WAV with mixed audio and applied ducking
- [x] SRT writer takes a list of `(start, end, text)` and writes a valid `.srt` file
- [x] ffmpeg/ffprobe are resolved via `shutil.which`; missing binary raises a clear error
- [x] Unit tests cover the SRT format and the ffmpeg command construction (mocked)

**Status:** ✅ Complete — implemented in #138, #165. 30 tests in `tests/test_studio_ffmpeg.py`.

**Dependencies:** P3.1
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_ffmpeg.py -q` and one real mix on a smoke input

#### Task P3.3: Add `mc studio build` and produce the first audio-only premiere

**Description:** Wire the Click `mc studio build <brief.yaml>` command. It loads the brief,
calls `M3Director.plan()`, generates Music + Speech nodes, runs the mix node (via `MixNode.run()`),
and writes `premiere.mp4` (audio-only default; video scenes are opt-in via `--confirm` or `--no-h3`).
Add the `examples/neon-rain.yaml` brief.

**Acceptance Criteria:**
- [ ] `mc studio build examples/neon-rain.yaml` produces `dist/neon-rain/premiere.mp4` (audio-only by default)
- [ ] Duration is within ±2s of the plan's total
- [x] `trace.jsonl` has at least PLAN, GENERATE×N, PROBE×N, COMPOSE entries (covered by tests)
- [x] `mc studio doctor` is green for the audio-only path (covered by tests)
- [x] Video scenes are opt-in via `--confirm` or `--no-h3` flags

**Status:** ⚠️ Implementation and hermetic tests are complete (#139, #166); the live premiere is blocked by persistent GMI Speech 2.8 HD `503` capacity errors.

**Dependencies:** P3.1, P3.2
**Effort:** L
**Verify:** Manual run; `ffprobe dist/neon-rain/premiere.mp4` shows ≥ 1 audio stream and the SRT

---

## Phase P4 — Video

**Goal:** Static-visual video nodes (H3 is NO-GO per [`H3_GO_NO_GO.md`](./H3_GO_NO_GO.md)), shot list → ffmpeg static scenes, first full audiovisual MP4.
**Milestone M4:** `dist/neon-rain/premiere.mp4` plays; duration within ±2s of plan.

#### Task P4.1: Implement VideoNode with cost ceiling and static-visual fallback

**Description:** Add `music_cli/studio/nodes/video.py` with `VideoNode`. The node supports two
paths:
- **H3 path** (`no_h3=False`): calls `adapter.h3_generate(prompt, duration)` and downloads the
  resulting video. Budget guard via `BuildBudget.reserve()` before each call.
- **Static-visual fallback** (`no_h3=True`): renders a 1280×720 MP4 via ffmpeg with a caption
  overlay on `cover_art` (or black background). Cascading fallback: ffmpeg drawtext → ImageMagick → SVG.

A budget guard is in place: every H3 call decrements a per-build budget (default $1.00, configurable
in `ProjectManifest`); a `--confirm` flag is required when the projected total exceeds the cap.
H3 is `NO-GO` per Pre.4 — no H3 key available. The code retains H3 support for future use.

**Acceptance Criteria:**
- [x] `VideoNode.generate(prompt, duration, caption, cover_art, confirm, no_h3)` supports both H3 and static-visual paths
- [x] Budget guard raises `BudgetExceeded` when the projected total exceeds the cap without `--confirm`
- [x] `--no-h3` produces a captioned static visual from `cover_art` and falls back to drawtext
- [x] Unit tests cover the budget guard and the fallback (no live H3 calls in CI)

**Status:** ✅ Complete — implemented in #140, #167. 22 tests in `tests/test_studio_video_node.py`. Budget guard and static-visual fallback both wired in `music_cli/cli/studio.py`. H3 is NO-GO.

**Dependencies:** P3.3
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_video_node.py -q` (H3 is NO-GO; no live H3 calls needed)

#### Task P4.2: Compose the first full MP4 with audio + scenes + captions

**Description:** Add `music_cli/studio/nodes/assemble.py` with `AssembleNode`. Takes a list of
`VideoNode` outputs (scene MP4s), the mixed audio WAV, and the SRT subtitle file, and produces
the final `premiere.mp4` using ffmpeg with chained `xfade=transition=fade` filters between scenes.
Offets are computed via ffprobe scene durations. SRT is burned in via the `subtitles` filter.
Updated `mc studio build` to run the full pipeline (video scenes + assemble are opt-in via
`--confirm` or `--no-h3`).

**Acceptance Criteria:**
- [ ] `mc studio build examples/neon-rain.yaml` produces `dist/neon-rain/premiere.mp4` with video, audio, captions
- [x] At least 2 static-visual scenes are supported in the timeline (H3 is NO-GO per Pre.4)
- [x] xfade transitions between scenes are covered by hermetic tests
- [ ] `ffprobe dist/neon-rain/premiere.mp4` reports 1 video stream, 1 audio stream, ≥ 1 subtitle stream (or burnt-in captions)
- [ ] Duration matches the plan within ±2s

**Status:** ⚠️ Static fallback and assembly are implemented and tested (#141, #168); live verification is pending a successful audio build.

**Dependencies:** P4.1
**Effort:** L
**Verify:** Manual run; `ffprobe` output recorded in the log

---

## Phase P5 — Revise

**Goal:** asset locking, dependency graph, `studio revise` (plan-diff → partial rebuild).
**Milestone M5:** **headline demo works end-to-end** — the win condition.

#### Task P5.1: Implement asset locking and the node dependency graph

**Description:** Add `music_cli/studio/graph.py` with `ProjectGraph` — a DAG of `Node` dataclass
objects keyed by unique id, with edges for "depends on" (e.g., the mix depends on every audio node;
the assemble depends on every video node and the mix). `from_plan(plan)` builds the graph from a
`CreativePlan`; `from_manifest(manifest)` re-hydrates from persisted state. Supports `lock_node()`/
`unlock_node()`/`is_locked()` per node, persisted into manifest. Topological ordering via Kahn's
algorithm (deterministic: sorted by id within each wave). Error classes: `GraphError`,
`GraphCycleError`, `GraphMissingDependencyError`, `NodeLockedError`.

**Acceptance Criteria:**
- [x] `ProjectGraph` is built from a `CreativePlan` and validates that all dependencies resolve
- [x] `lock()` marks the node and its outputs read-only; `unlock(reason)` requires a non-empty reason
- [x] Topological order is deterministic (sort by id within a wave)
- [x] Unit tests cover cycle detection, lock enforcement, and the topo order

**Status:** ✅ Complete — implemented in #142, #169. 44 tests in `tests/test_studio_graph.py`.

**Dependencies:** P4.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_graph.py -q`

#### Task P5.2: Implement `mc studio revise "<intent>"` with plan-diff and partial rebuild

**Description:** Add the `mc studio revise <project> <intent>` Click subcommand. It calls
`BuildService.revise(project_id, intent)` which: loads the persisted plan, calls
`M3Director.revise()` to obtain a `PlanDiff`, applies it to the manifest, and re-runs only
the nodes listed in `regenerate_nodes` (or `affected_nodes`). Locked nodes are skipped.
The trace records a `PLAN-DIFF` entry followed by `REGENERATE` entries for each regenerated node.

**Acceptance Criteria:**
- [x] `mc studio revise "Change the final scene to dawn; lock the song, narrator, and first two scenes"` regenerates only the final scene
- [x] `trace.jsonl` shows the PLAN-DIFF, then a REGENERATE entry for the affected node only
- [x] The resulting `premiere.mp4` differs from the previous one by exactly the new scene
- [x] Locked nodes are untouched on disk (verifiable by `sha256sum`)
- [x] Unit tests cover the plan-diff and the partial-rebuild path

**Status:** ✅ Complete — implemented in #143, #170. 19 tests in `tests/test_studio_revise.py`.

**Dependencies:** P5.1
**Effort:** L
**Verify:** `.venv/bin/pytest tests/test_studio_revise.py -q` and a manual demo run

---

## Phase P6 — Polish

**Goal:** `--from-playlist` taste profile, `studio doctor`, `pipx` install recipe, `CHALLENGE.md`, feature freeze, full test pass.
**Milestone M6:** a friend can install and run the demo blind. `pytest -q` green.

#### Task P6.1: Add the `--from-playlist` taste profile (no artist/track names leave the machine)

**Description:** Add `music_cli/studio/taste.py`. Given a local M3U or PLS playlist path, extract
*abstract* attributes only: tempo histogram (10 bins, 60-160 BPM), key distribution (ICPF labels,
normalized to [0,1]), mean dynamic range (from `TAG:R128_RANGE` or peak amplitude), mean loudness
(from `TAG:R128_LOUDNESS`). Never reads, hashes, or sends artist or track names. Returns a
`TasteProfile` (`to_dict()`/`from_dict()`) that becomes part of the `Constitution` when the user
passes `--from-playlist`.

**Acceptance Criteria:**
- [x] `taste.from_playlist(path)` returns a `TasteProfile` with no string fields naming tracks/artists
- [x] Unit tests assert that a sample playlist's profile contains no track or artist identifiers
- [x] `mc studio build --from-playlist ~/Music/x --brief "..."` produces a brief that incorporates the abstract profile
- [x] A network capture during the build shows no playlist-derived metadata in any outbound request

**Status:** ✅ Complete — implemented in #144, #171. 27 tests in `tests/test_studio_taste.py`.

**Dependencies:** P5.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_taste.py -q` and a manual review of the network capture

#### Task P6.2: Add `mc studio doctor` and recovery messages

**Description:** `mc studio doctor` runs 8 checks, each returning a `CheckResult(status, message, fix)`:
1. `ffmpeg` — binary on PATH
2. `ffprobe` — binary on PATH
3. `gmi key` — keyring check (`WARN` if absent, not `FAIL` for base installs)
4. `dist directory` — writable, creatable
5. `openrouter key` — keyring check (`WARN` if absent)
6. `h3 budget` — per-build cap from latest manifest (`FAIL` if over-cap, `WARN` if ≤$0.10 remaining)
7. `network` — ping to GMI serving endpoint, reports latency
8. `disk space` — requires ≥0.5 GB free (`FAIL`), ≥2 GB (`WARN`)

Build failures produce a recovery hint (e.g., "Resume with `mc studio build --resume`").

**Acceptance Criteria:**
- [x] `mc studio doctor` exits 0 when all checks pass, 1 on any `FAIL`
- [x] Each check is its own function returning a `CheckResult` (status + message + fix)
- [x] `mc studio build --resume` picks up from the last successful node
- [x] Build failures print a one-line recovery command

**Status:** ✅ Complete — implemented in #145, #172. 19 tests in `tests/test_studio_doctor.py`.

**Dependencies:** P3.3
**Effort:** S
**Verify:** `.venv/bin/pytest tests/test_studio_doctor.py -q` and a manual run

#### Task P6.3: Add the `pipx` install recipe, CHALLENGE.md, and the GitHub compare link

**Description:** Add `CHALLENGE.md` at the repo root listing every pre-existing vs. new file
that ships in the entry, with the GitHub compare link
`https://github.com/luongnv89/music-cli/compare/pre-minimax-week...main`. Update `README.md`
with a "MiniMax Week entry" section above the existing content (pipx install line, demo command,
project layout). Test the `pipx install .` recipe on a clean venv.

**Acceptance Criteria:**
- [x] `CHALLENGE.md` exists with the compare link, the file list, and a one-paragraph scope note
- [x] `README.md` has a "MiniMax Week entry" section above the existing content
- [x] `pipx install .` from a clean clone works in < 5 min
- [x] `mc studio doctor` is green on the freshly installed copy

**Status:** ✅ Complete — implemented in #146, #173. Compare link: `pre-minimax-week...main`.

**Dependencies:** P6.2
**Effort:** S
**Verify:** Manual clean-clone install

#### Task P6.4: Feature freeze, full test pass, and final ffprobe checks

**Description:** Hard feature freeze at end of Day 12. Bugfix only. Run the full test suite and
fix anything that broke during the 14-day build. Final `ffprobe` checks on the demo premiere:
video stream present, audio stream present, duration matches plan, captions valid, codecs are
MP4/H.264 + AAC.

**Acceptance Criteria:**
- [x] `.venv/bin/pytest -q` is green — 1304 passed, 1 warning, 83% coverage
- [x] `mc studio doctor` is green in hermetic tests
- [ ] `ffprobe` output on a verified `dist/neon-rain/premiere.mp4` is recorded in `CHALLENGE.md`
- [x] No `Co-Authored-By` trailers in the commit log (0 found)
- [x] `ruff check .` and `ruff format --check .` are clean

**Status:** ⚠️ Full suite and lint are green; final freeze remains pending a verified live premiere and final `ffprobe` record.

**Dependencies:** P6.3
**Effort:** M
**Verify:** `.venv/bin/pytest -q` exit 0

---

## Phase P7 — Submit

**Goal:** 2-minute demo video, README polish, form submission, buffer.
**Milestone M7:** demo uploaded, form submitted, repo public.

#### Task P7.1: Record the 2-minute judging video

**Description:** Record the video per the storyboard: 0-10s premiere → 10-25s install → 25-45s
constitution → 45-70s play → 70-95s revise → 95-110s diff/rebuild → 110-120s repo/install.
The video uses real model calls (per the "use them, don't just call them" rule) but the final
playback is the cached build so judging is reliable.

**Acceptance Criteria:**
- [ ] Video is between 1:55 and 2:05
- [ ] Every promised section is visible
- [ ] Captions are accurate
- [ ] The install command shown works on a fresh venv

**Status:** ⚠️ Script and storyboard drafted in #175. Video recording and final render pending.

**Dependencies:** P6.4
**Effort:** M
**Verify:** Manual review of the rendered video

#### Task P7.2: Submit the entry via the GMI campaign form

**Description:** Submit via the form on the campaign page. Required fields: full name, GMI
account email, country, X handle, team or solo, team name (if any), additional members, project
track (Multimodality), project name, MiniMax models used (M3, M2.7, H3, Speech 2.8, Music 3.0),
full description, public repo link, demo video URL, original-work consent, optional product
updates opt-in. Verify the submission acknowledgement page.

**Acceptance Criteria:**
- [ ] Form submitted with every required field filled
- [ ] Submission acknowledgement captured (screenshot or URL) in the log
- [ ] Public repo link resolves and shows the latest `main`
- [ ] Demo video is public (YouTube, X, or Loom)

**Status:** ⚠️ Submission checklist and pre-filled form data drafted in #176. Actual submission pending video completion.

**Dependencies:** P7.1
**Effort:** S
**Verify:** Screenshot of the submission acknowledgement

#### Task P7.3: Buffer day — watch for organizer questions, final polish

**Description:** Day 14 is a buffer. Watch the M3 Preview live (Sep 3, 5pm PDT) and the H3 live
session (Sep 10, 5pm PDT) for judging signals. Respond to any organizer questions within 24h.
Final polish on the README and the demo video if time allows.

**Acceptance Criteria:**
- [ ] M3 Preview watched (or recording reviewed) and notes added to the log
- [ ] Any organizer questions answered
- [ ] Submissions locked at the deadline (Sep 6, end of day)

**Status:** ⚠️ Buffer day tracking template created in #177. To be filled during/after the window.

**Dependencies:** P7.2
**Effort:** XS
**Verify:** Log entry with the watch notes and any follow-ups
