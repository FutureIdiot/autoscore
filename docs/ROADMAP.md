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
- Empty project creation, provided artifact attachment, provided vocals, and
  provided tempo timeline support.
- Mock `separateAudio`, `estimateTempo`, and `detectPhrases` runners wired
  through controller/TUI send execution.
- Timeline foundation models and tests.

## Current Development State

- `create` in the TUI creates project workspaces from `importDir` or `inbox/`,
  or creates an empty workspace when no files are present.
- `send` dispatches currently registered artifacts to ready nodes. It can run
  the ready pipeline, a single task, or a downstream chain with `&`; `!` forces
  reruns.
- Readiness only blocks on required artifacts. Optional inputs such as lyrics,
  manual metadata, or tempo context are allowed to be missing and should produce
  warnings from the receiving task.
- `detectPhrases` currently requires only `artifact_vocals_wav`; missing tempo
  falls back to 120 BPM, missing meter falls back to 4/4, and missing lyrics are
  reported as warnings.
- The current `create` implementation still guesses whether inbox audio should
  be treated as original audio or provided vocals. This is the next design
  cleanup.

## Next Steps

1. Pending Input Binding

   Move artifact role assignment out of `create`. `create` should register
   incoming files as pending project inputs. `send <task>` should bind pending
   files to the artifacts required by that task:

   ```text
   send separateAudio    pending audio -> artifact_original_audio
   send detectPhrases    pending audio -> artifact_vocals_wav
   ```

   This keeps single-node tests and full-pipeline runs on the same mechanism.

2. Expand Mock Task Runners

   Add local/mock runners for the remaining major task types:

   ```text
   runGame
   runLyricFA
   alignPhrase
   stitchPhrases
   buildScoreJson
   ```

3. End-to-End Mock Pipeline

   Run a full project through mock separator, mock timeline, mock GAME, mock
   LyricFA, alignment, stitching, and placeholder score export.

4. Real Timeline Analysis

   Add tempo and phrase detection backends. Start with lightweight mocked or
   librosa-based behavior, then evaluate Essentia when needed.

5. External Integrations

   Integrate GAME and LyricFA behind their package boundaries. Keep their local
   Python paths and model paths in package config or provenance, not in project
   manifests.

6. Score Export

   Implement canonical score schema models, validation, bar generation, and
   `score.json` export after the mock pipeline is stable.

## Current Non-Goals

- No real separator backend yet.
- No WebUI yet.
- No score renderer yet.
- No Signal bridge implementation yet.
- No heavy audio or ML dependencies in the core environment yet.
