# Autoscore Roadmap

This roadmap reflects the current repository state. It intentionally replaces
older private implementation lists that may exist locally under
`.designdocuments/`.

## Completed Foundation

- Python 3.12 project managed by `uv`.
- Core artifact references.
- Project manifest and manifest migration entry point.
- Structured warning/error records.
- Runtime task envelope/result contracts.
- Package config loading from JSON and TOML.
- Runtime controller and static local node registry.
- Dependency-free development CLI/TUI shell.
- Local artifact registry and materialization.
- CLI project creation and TUI create/send project workflow.
- Artifact-driven dispatch with required and optional task input contracts.
- Pending input binding at send time for task-specific audio artifact roles.
- TUI project info view/edit for manual tempo and meter.
- Empty project creation, pending input registration, provided artifact
  attachment, and provided tempo timeline support.
- Mock `separateAudio`, `estimateTempo`, `detectPhrases`, `analyzeMidi`,
  `analyzeLyrics`, and `buildScoreJson` runners wired through controller/TUI
  send execution.
- Timeline foundation models and tests.

## Current Development State

- `create` in the TUI creates project workspaces from `importDir` or `inbox/`,
  or creates an empty workspace when no files are present. Initial files are
  grouped by prefix, so `songname.wav`, `songname.txt`, and
  `songname_vox.wav` create one workspace. Discovered files are kept as pending
  inputs until send-time registration.
- `send` dispatches project artifacts to numbered or named node tasks. It can
  run the ready pipeline, a single task, or a downstream chain with `&`; `!`
  forces reruns.
- If a task's expected output artifacts already exist, `send` skips that task
  and continues downstream. Adding `!` forces the task to rerun and overwrite
  those outputs.
- Before a task runs, pending inputs are registered as artifacts from filename
  purpose:

   ```text
  *vox* or *vocal*                 -> artifact_vocals_wav
  *instrument* or *accompaniment*  -> artifact_accompaniment_wav
  *.txt                            -> artifact_lyrics_txt
  plain audio                      -> artifact_original_audio
  ```

- `info` in the project TUI shows and edits manual tempo and meter, updating
  the manifest and manual metadata/tempo artifacts.
- Readiness only blocks on required artifacts. Optional inputs such as lyrics,
  manual metadata, or tempo context are allowed to be missing and should produce
  warnings from the receiving task.
- `detectPhrases` currently requires only `artifact_vocals_wav`; missing tempo
  falls back to 120 BPM, missing meter falls back to 4/4, and missing lyrics are
  reported as warnings.

## Next Steps

1. Expand Mock Task Runners

   Resolve the MIDI-to-lyrics alignment model, then add local/mock runners for
   the remaining timeline task types:

   ```text
   alignPhrase
   stitchPhrases
   ```

2. End-to-End Mock Pipeline

   Run a full project through mock separator, mock timeline, mock MIDI
   analysis, mock lyric analysis, alignment, stitching, and placeholder score
   export. The current `buildScoreJson` mock can already export from analysis
   artifacts, and should switch to aligned/stitched inputs after those nodes
   are settled.

3. Rerun and Resume Behavior

   Clarify how forced reruns invalidate or preserve downstream artifacts, and
   make resumed cross-step execution predictable once more tasks exist.

4. Structured Problem Persistence

   Keep `TaskResult` warnings/errors as `ProblemRecord` objects and migrate
   durable controller/manifest warning and error persistence from plain strings
   to structured records after the mock pipeline is stable.

5. Real Timeline Analysis

   Add tempo and phrase detection backends. Start with lightweight mocked or
   librosa-based behavior, then evaluate Essentia when needed.

6. External Integrations

   Treat MIDI generation and lyric forced alignment as external user/tool
   steps. GAME and LyricFA can be recommended for those steps without becoming
   default Autoscore package dependencies.

7. Node Registry Serialization

   Add `to_dict`/`from_dict` support and file/remote loading for the
   deployment package -> node capability -> task type mapping described in
   `docs/ARCHITECTURE.md`.

8. Score Export

   Implement canonical score schema models, validation, bar generation, and
   real `score.json` export after the mock pipeline is stable.

## Current Non-Goals

- No real separator backend yet.
- No WebUI yet.
- No score renderer yet.
- No Signal bridge implementation yet.
- No heavy audio or ML dependencies in the core environment yet.
