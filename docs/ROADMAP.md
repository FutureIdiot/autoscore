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
- Timeline foundation models and tests.

## Next Steps

1. Local Artifact Registry

   Implement artifact id generation, hashing, lookup, and materialization for
   local tasks. Preserve `relativePath`, `uri`, `sha256`, and size metadata.

2. Project Creation

   Add a CLI/controller path to create a project workspace from input audio and
   lyrics. Write `manifest.json`, copy or register input artifacts, and mark
   `createProject` as succeeded.

3. Mock Task Runners

   Add local/mock runners for the major task types:

   ```text
   separateAudio
   estimateTempo
   detectPhrases
   runGame
   runLyricFA
   alignPhrase
   stitchPhrases
   buildScoreJson
   ```

4. Controller/TUI Step Execution

   Wire `AutoscoreController.run_step()` to task runners so the TUI can trigger
   a selected step and immediately show manifest/artifact changes.

5. End-to-End Mock Pipeline

   Run a full project through mock separator, mock timeline, mock GAME, mock
   LyricFA, alignment, stitching, and placeholder score export.

6. Real Timeline Analysis

   Add tempo and phrase detection backends. Start with lightweight mocked or
   librosa-based behavior, then evaluate Essentia when needed.

7. External Integrations

   Integrate GAME and LyricFA behind their package boundaries. Keep their local
   Python paths and model paths in package config or provenance, not in project
   manifests.

8. Score Export

   Implement canonical score schema models, validation, bar generation, and
   `score.json` export after the mock pipeline is stable.

## Current Non-Goals

- No real separator backend yet.
- No WebUI yet.
- No score renderer yet.
- No Signal bridge implementation yet.
- No heavy audio or ML dependencies in the core environment yet.
