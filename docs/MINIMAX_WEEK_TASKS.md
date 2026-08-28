# MiniMax Week × GMI Cloud — Plan tasks (companion to MINIMAX_WEEK_PLAN.md)

> Companion file to [`docs/MINIMAX_WEEK_PLAN.md`](./MINIMAX_WEEK_PLAN.md).
> This file is shaped for `/plan-to-issues` parsing: it uses `^#### Task <id>:` headings and a
> `## Phase <id> — <title>` heading for each phase. All content is copied verbatim from the plan;
> the plan remains the source of truth for prose and design.
> Source binding marker: `<!-- plan-to-issues:plan=docs/MINIMAX_WEEK_PLAN.md -->`

**Project:** music-cli
**Baseline:** Day 3 of 14 (Aug 26, 2026); baseline tag `pre-minimax-week` @ `1dbf3bb`.
**Test command of record:** `.venv/bin/pytest -q -p no:cacheprovider`
**Track:** Multimodality
**Window:** Aug 24 – Sep 6, 2026
**Critical path:** Pre.1 → Pre.2 → P1.1 → P1.2 → P2.1 → P3.1 → P4.1 → P4.2 → P5.1 → P5.2 → P7.1

---

## Phase Pre — De-risk

**Goal:** de-risk every model, decide H3, confirm pre-existing-repo eligibility, tag the baseline.
**Milestone ME:** `H3_GO_NO_GO.md` written; one real call to M3, Music 3.0, Speech 2.0 succeeded.

#### Task Pre.1: Tag the pre-minimax-week baseline and create the GMI account

**Description:** Tag the current HEAD as `pre-minimax-week` and record the SHA. Create a GMI Cloud
account (free) and capture the API key in `keyring` via a new `mc cloud` subcommand. `keyring` is not
yet a project dependency — add it to `[project.optional-dependencies]` as a new `gmi` extra
(`gmi = ["keyring>=24", "httpx>=0.27"]`). Do not commit the key, env vars, or any prompt that
contains it.

**Acceptance Criteria:**
- [ ] `git tag pre-minimax-week` is at the recorded SHA
- [ ] `mc cloud key set gmi` writes to `keyring` and the key is unreadable from a child process
- [ ] `mc cloud key get gmi` round-trips the value (smoke test only)
- [ ] `pyproject.toml` declares a new `gmi` extra including `keyring` and `httpx`

**Dependencies:** None
**Effort:** S
**Verify:** `git rev-parse pre-minimax-week && python -c "import keyring"`

#### Task Pre.2: Smoke-test M3, Music 3.0, Speech 2.8 with one real call each

**Description:** Run one real API call to each free model: M3 (text reasoning), Music 3.0 (song
generation), Speech 2.8 (text-to-speech). Capture latency, response format, polling needs, and
output format. Log the results in `docs/MINIMAX_WEEK_LOG.md` under Day 3. This is the de-risk gate —
if any free model is unreachable or unusable, the entry pivots to whatever is reachable.

**Acceptance Criteria:**
- [ ] One real M3 call returns text in < 30s
- [ ] One real Music 3.0 call returns audio in the documented format
- [ ] One real Speech 2.8 call returns audio in the documented format
- [ ] All three results are logged with timestamp, latency, size, format
- [ ] One H3 call attempted if budget allows; H3 cost recorded

**Dependencies:** Pre.1
**Effort:** S
**Verify:** Three files written under `dist/_smoke/`, all present

#### Task Pre.3: Confirm pre-existing-repo eligibility with organizers

**Description:** Send a 30-second question to the organizers via the campaign form or contact
email: "Is a pre-existing public repo allowed if the GMI/MiniMax integration, the `studio` command
group, and the audiovisual pipeline are built during the 14-day window?" Record the answer in
`docs/MINIMAX_WEEK_LOG.md` under Day 3.

**Acceptance Criteria:**
- [ ] Question sent through the documented channel
- [ ] Reply received and pasted into the log
- [ ] If rejected, `feat/minimax-week-studio` work is relocated to a fresh repo per the fallback

**Dependencies:** None
**Effort:** XS
**Verify:** Log entry exists with a date and an answer (yes / pending / no + action)

#### Task Pre.4: Decide H3 go/no-go and write `H3_GO_NO_GO.md`

**Description:** H3 is a paid per-request model. If cost or latency is unacceptable, the entry
degrades to "audio + captions + static H3 thumbnail" or pure audio+caption premiere, still inside
the Multimodality track. Decision must be written into `docs/H3_GO_NO_GO.md` by end of Day 4.

**Acceptance Criteria:**
- [ ] `docs/H3_GO_NO_GO.md` exists with one of `GO`, `NO-GO` (degrade), or `DEFER` (decide Day 7)
- [ ] If `GO`: estimated H3 cost per build, budget cap, and `--confirm` flag plan recorded
- [ ] If `NO-GO`: fallback path documented (audio-only MP4, captioned, ffmpeg static visual)

**Dependencies:** Pre.2
**Effort:** XS
**Verify:** `test -f docs/H3_GO_NO_GO.md && head -1 docs/H3_GO_NO_GO.md | grep -E "GO|NO-GO|DEFER"`

---

## Phase P1 — Adapters

**Goal:** schemas, GMI/OpenRouter adapters, polling, retries, resumable cache, keyring integration.
**Milestone M1:** one real audio-only build (`Music 3.0` + `Speech 2.8`) end-to-end.

#### Task P1.1: Define CreativePlan, Constitution, ProjectManifest, PlanDiff JSON schemas

**Description:** Add `music_cli/studio/schemas.py` with strict JSON schemas for the four core
artifacts. Schemas are the contract between M3 and the runtime; a parse failure on any field must
trigger a re-prompt, not a silent drop. Use Pydantic or `jsonschema`; pick whichever is already in
the dep tree.

**Acceptance Criteria:**
- [ ] `music_cli/studio/schemas.py` exports `CreativePlan`, `Constitution`, `ProjectManifest`, `PlanDiff`
- [ ] Each schema has a `validate()` method that returns a list of errors
- [ ] Unit tests cover at least 3 valid and 3 invalid examples per schema
- [ ] Schemas are importable without any of the GMI deps installed

**Dependencies:** Pre.1
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_schemas.py -q`

#### Task P1.2: Implement GMI Cloud + OpenRouter adapters with polling and retries

**Description:** Add `music_cli/cloud/gmi.py` (`GMIAdapter` for M3, Music 3.0, Speech 2.8, H3) and
`music_cli/cloud/openrouter.py` (`OpenRouterAdapter` for M3, M2.7, Speech 2.8). Both must support
async polling (most of these models are async jobs), exponential backoff with idempotency keys,
and a resumable on-disk cache (`music_cli/cloud/strategy_cache.py` already exists — extend it).

**Acceptance Criteria:**
- [ ] `GMIAdapter` exposes `m3_plan`, `m3_critique`, `music3_generate`, `speech28_synthesize`, `h3_generate`
- [ ] `OpenRouterAdapter` exposes `m3_chat`, `m27_chat`, `speech28_synthesize`
- [ ] Both have a `run()` method that retries up to 3 times with exponential backoff
- [ ] Polling is async; cancellation is cooperative
- [ ] Cache key is the model + prompt hash + parameters; cache hit returns instantly
- [ ] Unit tests against a recorded fixture (no live calls in CI)

**Dependencies:** P1.1
**Effort:** L
**Verify:** `.venv/bin/pytest tests/test_cloud_gmi.py tests/test_cloud_openrouter.py -q`

#### Task P1.3: Add the `mc cloud` subcommand and keyring-backed secret storage

**Description:** Add `music_cli/cloud/secrets.py` (keyring wrapper) and `music_cli/cli/cloud.py`
(Click group). Public surface: `mc cloud key set <provider>`, `mc cloud key get <provider>`,
`mc cloud ping` (calls each adapter with a trivial request and reports success/latency).

**Acceptance Criteria:**
- [ ] `mc cloud key set gmi` writes the key to the OS keyring; `mc cloud key get gmi` reads it
- [ ] `mc cloud ping` reports reachable/unreachable for each model
- [ ] No key value is ever printed to stdout or stored in a file
- [ ] `mc cloud --help` lists subcommands and examples

**Dependencies:** P1.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_cli_cloud.py -q` and a manual `mc cloud ping`

---

## Phase P2 — Director

**Goal:** M3 director with structured plan/critique/revise calls and a JSONL decision trace.
**Milestone M2:** M3 plan on a real brief; trace file looks right.

#### Task P2.1: Implement M3Director with plan, critique, revise

**Description:** Add `music_cli/studio/director.py` with `M3Director` class. Three methods:
- `plan(brief) -> CreativePlan` — call M3 with the brief, validate against the schema, retry on
  parse failure with a "re-output the exact JSON" instruction.
- `critique(plan, measurements) -> CritiqueReport` — call M3 with the plan + measured
  ffprobe results, return a structured report listing inconsistencies.
- `revise(plan, intent) -> PlanDiff` — call M3 with the plan + revision intent, return a diff
  describing which nodes are locked and which must regenerate.

All three must log every call (input hash, output hash, latency, retry count) to the trace.

**Acceptance Criteria:**
- [ ] `M3Director.plan(brief)` returns a `CreativePlan` validated against the schema
- [ ] `M3Director.critique(plan, measurements)` returns a `CritiqueReport` with at least `ok`, `issues[]`, `repairs[]`
- [ ] `M3Director.revise(plan, intent)` returns a `PlanDiff` with `locked_nodes[]`, `regenerate_nodes[]`
- [ ] On schema parse failure, the director retries up to 2 times with a corrective prompt
- [ ] All calls append to `trace.jsonl` with at least `step`, `model`, `ts`, `input_hash`, `output_hash`, `latency_ms`

**Dependencies:** P1.2
**Effort:** L
**Verify:** `.venv/bin/pytest tests/test_studio_director.py -q` plus one real M3 plan in `dist/_smoke/`

#### Task P2.2: Implement trace.jsonl writer and project directory layout

**Description:** Add `music_cli/studio/trace.py` and the on-disk project layout under
`dist/<project>/`. Every M3 call, every generation, every probe, every repair, every assemble
writes one line of JSON to `trace.jsonl`. Lines are append-only; rotation is not needed (a
premiere build produces ~50 lines).

**Acceptance Criteria:**
- [ ] `TraceWriter` is an append-only context manager
- [ ] Each line is valid JSON with `ts`, `step`, `model`, `node_id`, `latency_ms`, `payload_hash`
- [ ] `dist/<project>/` layout matches the spec: `plan.yaml`, `trace.jsonl`, `nodes/`, `premiere.mp4`
- [ ] `mc studio plan <project>` reads `plan.yaml` and pretty-prints it
- [ ] `mc studio trace <project>` reads `trace.jsonl` and renders a human-readable table

**Dependencies:** P2.1
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_trace.py -q`

---

## Phase P3 — Audio

**Goal:** Music and Speech nodes, ffmpeg mix + captions, ffprobe node validation.
**Milestone M3:** first **audio-only** premiere (~60s) plays.

#### Task P3.1: Implement MusicNode and SpeechNode with the Node protocol

**Description:** Add `music_cli/studio/nodes/base.py` (`Node` protocol with `generate()`,
`probe()`, `lock()`), `music_cli/studio/nodes/music.py` (`MusicNode` → Music 3.0), and
`music_cli/studio/nodes/speech.py` (`SpeechNode` → Speech 2.8). Each node must write its output
into the project's `nodes/` directory, run a probe, and lock on success.

**Acceptance Criteria:**
- [ ] `Node` protocol has `generate()`, `probe()`, `lock()`, `unlock()`, `path`
- [ ] `MusicNode.generate(prompt, lyrics, duration)` calls Music 3.0, writes `nodes/song-N.wav`, runs `ffprobe`
- [ ] `SpeechNode.generate(text, voice, duration)` calls Speech 2.8, writes `nodes/narration-N.wav`, runs `ffprobe`
- [ ] A locked node refuses to regenerate without an explicit `unlock()`
- [ ] Unit tests cover the protocol and the two nodes against a recorded fixture

**Dependencies:** P2.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_nodes.py -q`

#### Task P3.2: Implement ffmpeg mix node and SRT caption generation

**Description:** Add `music_cli/studio/nodes/ffmpeg.py` with `MixNode` (uses ffmpeg `amix` for
audio layering, `sidechaincompress` for ducking under narration) and a helper that takes the
plan's narration text and writes `nodes/captions.srt`. The mix node produces a final WAV for the
audio-only pipeline; the SRT is reused when the video nodes land in P4.

**Acceptance Criteria:**
- [ ] `MixNode.run(nodes, captions, out_path)` produces a single WAV with mixed audio and applied ducking
- [ ] SRT writer takes a list of `(start, end, text)` and writes a valid `.srt` file
- [ ] ffmpeg/ffprobe are resolved via `shutil.which`; missing binary raises a clear error
- [ ] Unit tests cover the SRT format and the ffmpeg command construction (mocked)

**Dependencies:** P3.1
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_ffmpeg.py -q` and one real mix on a smoke input

#### Task P3.3: Add `mc studio build` and produce the first audio-only premiere

**Description:** Wire the Click `mc studio build <brief.yaml>` command. It loads the brief,
calls `M3Director.plan()`, generates Music + Speech nodes, runs the mix node, and writes
`premiere.mp4` (audio-only for now — the video pipeline lands in P4). Add the `examples/neon-rain.yaml`
brief.

**Acceptance Criteria:**
- [ ] `mc studio build examples/neon-rain.yaml` produces `dist/neon-rain/premiere.mp4` with audio + captions
- [ ] Duration is within ±2s of the plan's total
- [ ] `trace.jsonl` has at least PLAN, GENERATE×N, PROBE×N, COMPOSE entries
- [ ] `mc studio doctor` is green for the audio-only path

**Dependencies:** P3.1, P3.2
**Effort:** L
**Verify:** Manual run; `ffprobe dist/neon-rain/premiere.mp4` shows ≥ 1 audio stream and the SRT

---

## Phase P4 — Video

**Goal:** H3 video nodes, shot list → H3 prompts, first full audiovisual MP4.
**Milestone M4:** `dist/neon-rain/premiere.mp4` plays; duration within ±2s of plan.

#### Task P4.1: Implement VideoNode with H3 and a cost ceiling

**Description:** Add `music_cli/studio/nodes/video.py` with `VideoNode` that calls H3. Wrap the
H3 cost in a budget guard: every call decrements a per-build budget (default $1.00, configurable
in `ProjectManifest`); a `--confirm` flag is required when the projected total exceeds the cap.
A `--no-h3` flag falls back to a static visual from the plan's `cover_art` field (or a generated
SVG via ffmpeg drawtext) so the entry still works when H3 is `NO-GO` per `H3_GO_NO_GO.md`.

**Acceptance Criteria:**
- [ ] `VideoNode.generate(prompt, duration)` calls H3, writes `nodes/scene-N.mp4`, runs `ffprobe`
- [ ] Budget guard raises `BudgetExceeded` when the projected total exceeds the cap without `--confirm`
- [ ] `--no-h3` produces a captioned static visual from `cover_art` and falls back to drawtext
- [ ] Unit tests cover the budget guard and the fallback (no live H3 calls in CI)

**Dependencies:** P3.3
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_video_node.py -q` and one real H3 call in `dist/_smoke/`

#### Task P4.2: Compose the first full MP4 with audio + scenes + captions

**Description:** Extend `MixNode` (or add a new `AssembleNode`) to take a list of `VideoNode`
outputs, the audio mix, and the SRT, and produce the final `premiere.mp4` using ffmpeg with
xfade transitions between scenes. Update `mc studio build` to run the full pipeline.

**Acceptance Criteria:**
- [ ] `mc studio build examples/neon-rain.yaml` produces `dist/neon-rain/premiere.mp4` with video, audio, captions
- [ ] At least 2 H3 scenes are in the timeline (or the static-visual fallback if H3 is NO-GO)
- [ ] xfade transitions between scenes are visible in playback
- [ ] `ffprobe dist/neon-rain/premiere.mp4` reports 1 video stream, 1 audio stream, ≥ 1 subtitle stream (or burnt-in captions)
- [ ] Duration matches the plan within ±2s

**Dependencies:** P4.1
**Effort:** L
**Verify:** Manual run; `ffprobe` output recorded in the log

---

## Phase P5 — Revise

**Goal:** asset locking, dependency graph, `studio revise` (plan-diff → partial rebuild).
**Milestone M5:** **headline demo works end-to-end** — the win condition.

#### Task P5.1: Implement asset locking and the node dependency graph

**Description:** Add `music_cli/studio/graph.py` with `ProjectGraph` — a DAG of `Node` objects
keyed by id, with edges for "depends on" (e.g., the mix depends on every audio node; the assemble
depends on every video node and the mix). Add `lock()`/`unlock()` to `Node` and persist the lock
state into `ProjectManifest`. A locked node refuses `generate()` without an explicit
`unlock(reason)`.

**Acceptance Criteria:**
- [ ] `ProjectGraph` is built from a `CreativePlan` and validates that all dependencies resolve
- [ ] `lock()` marks the node and its outputs read-only; `unlock(reason)` requires a non-empty reason
- [ ] Topological order is deterministic (sort by id within a wave)
- [ ] Unit tests cover cycle detection, lock enforcement, and the topo order

**Dependencies:** P4.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_graph.py -q`

#### Task P5.2: Implement `mc studio revise "<intent>"` with plan-diff and partial rebuild

**Description:** Add the `mc studio revise` Click subcommand. It calls `M3Director.revise()` on
the existing plan, applies the `PlanDiff` to `ProjectManifest`, and re-runs only the affected
nodes. Unaffected nodes stay locked. The trace must clearly show which nodes were regenerated
and which stayed.

**Acceptance Criteria:**
- [ ] `mc studio revise "Change the final scene to dawn; lock the song, narrator, and first two scenes"` regenerates only the final scene
- [ ] `trace.jsonl` shows the PLAN-DIFF, then a REGENERATE entry for the affected node only
- [ ] The resulting `premiere.mp4` differs from the previous one by exactly the new scene
- [ ] Locked nodes are untouched on disk (verifiable by `sha256sum`)
- [ ] Unit tests cover the plan-diff and the partial-rebuild path

**Dependencies:** P5.1
**Effort:** L
**Verify:** `.venv/bin/pytest tests/test_studio_revise.py -q` and a manual demo run

---

## Phase P6 — Polish

**Goal:** `--from-playlist` taste profile, `studio doctor`, `pipx` install recipe, `CHALLENGE.md`, feature freeze, full test pass.
**Milestone M6:** a friend can install and run the demo blind. `pytest -q` green.

#### Task P6.1: Add the `--from-playlist` taste profile (no artist/track names leave the machine)

**Description:** Add `music_cli/studio/taste.py`. Given a local playlist path, extract *abstract*
attributes only: tempo histogram, key distribution, dynamic range, mean loudness. Never read,
hash, or send artist or track names. The output is a `TasteProfile` that becomes part of the
`Constitution` when the user passes `--from-playlist`.

**Acceptance Criteria:**
- [ ] `taste.from_playlist(path)` returns a `TasteProfile` with no string fields naming tracks/artists
- [ ] Unit tests assert that a sample playlist's profile contains no track or artist identifiers
- [ ] `mc studio build --from-playlist ~/Music/x --brief "..."` produces a brief that incorporates the abstract profile
- [ ] A network capture during the build shows no playlist-derived metadata in any outbound request

**Dependencies:** P5.2
**Effort:** M
**Verify:** `.venv/bin/pytest tests/test_studio_taste.py -q` and a manual review of the network capture

#### Task P6.2: Add `mc studio doctor` and recovery messages

**Description:** `mc studio doctor` reports on: GMI key (set, valid), OpenRouter key (optional),
FFmpeg (installed, version), H3 budget (per-day remaining, per-build cap), network (ping to
GMI), and disk space (for `dist/`). Every check must have a clear `OK`/`WARN`/`FAIL` line and a
remediation hint. Build failures and network errors during `studio build` must produce a recovery
hint (e.g., "Resume with `mc studio build --resume`").

**Acceptance Criteria:**
- [ ] `mc studio doctor` exits 0 when all checks pass, 1 on any `FAIL`
- [ ] Each check is its own function returning a `CheckResult` (status + message + fix)
- [ ] `mc studio build --resume` picks up from the last successful node
- [ ] Build failures print a one-line recovery command

**Dependencies:** P3.3
**Effort:** S
**Verify:** `.venv/bin/pytest tests/test_studio_doctor.py -q` and a manual run

#### Task P6.3: Add the `pipx` install recipe, CHALLENGE.md, and the GitHub compare link

**Description:** Add `CHALLENGE.md` at the repo root listing every pre-existing vs. new file
that ships in the entry, with the GitHub compare link
`https://github.com/luongnv89/music-cli/compare/pre-minimax-week...main`. Update `README.md`
with a one-paragraph entry pitch, the `pipx install` line, the demo command, and a screenshot
or ASCII-art of the project layout. Test the `pipx install` recipe on a clean venv.

**Acceptance Criteria:**
- [ ] `CHALLENGE.md` exists with the compare link, the file list, and a one-paragraph scope note
- [ ] `README.md` has a "MiniMax Week entry" section above the existing content
- [ ] `pipx install .` from a clean clone works in < 5 min
- [ ] `mc studio doctor` is green on the freshly installed copy

**Dependencies:** P6.2
**Effort:** S
**Verify:** Manual clean-clone install

#### Task P6.4: Feature freeze, full test pass, and final ffprobe checks

**Description:** Hard feature freeze at end of Day 12. Bugfix only. Run the full test suite and
fix anything that broke during the 14-day build. Final `ffprobe` checks on the demo premiere:
video stream present, audio stream present, duration matches plan, captions valid, codecs are
MP4/H.264 + AAC.

**Acceptance Criteria:**
- [ ] `.venv/bin/pytest -q` is green
- [ ] `mc studio doctor` is green
- [ ] `ffprobe` output on `dist/neon-rain/premiere.mp4` is recorded in `CHALLENGE.md`
- [ ] No `Co-Authored-By` trailers in the commit log
- [ ] `ruff check .` and `ruff format --check .` are clean

**Dependencies:** P6.3
**Effort:** M
**Verify:** `.venv/bin/pytest -q` exit 0

---

## Phase P7 — Submit

**Goal:** 2-minute demo video, README polish, form submission, buffer.
**Milestone M7:** demo uploaded, form submitted, repo public.

#### Task P7.1: Record the 2-minute judging video

**Description:** Record the video per the storyboard in `MINIMAX_WEEK_PLAN.md`: 0-10s premiere →
10-25s install → 25-45s constitution → 45-70s play → 70-95s revise → 95-110s diff/rebuild →
110-120s repo/install. The video uses real model calls (per the "use them, don't just call them"
rule) but the final playback is the cached build so judging is reliable.

**Acceptance Criteria:**
- [ ] Video is between 1:55 and 2:05
- [ ] Every promised section is visible
- [ ] Captions are accurate
- [ ] The install command shown works on a fresh venv

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

**Dependencies:** P7.2
**Effort:** XS
**Verify:** Log entry with the watch notes and any follow-ups
