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
- CLI project creation and TUI import-directory project creation.
- Mock `separateAudio` and `estimateTempo` runners wired through controller/TUI step execution.
- Timeline foundation models and tests.

## Next Steps

1. Expand Mock Task Runners

   Add local/mock runners for the remaining major task types:

   ```text
   detectPhrases
   runGame
   runLyricFA
   alignPhrase
   stitchPhrases
   buildScoreJson
   ```

2. End-to-End Mock Pipeline

   Run a full project through mock separator, mock timeline, mock GAME, mock
   LyricFA, alignment, stitching, and placeholder score export.

3. Real Timeline Analysis

   Add tempo and phrase detection backends. Start with lightweight mocked or
   librosa-based behavior, then evaluate Essentia when needed.

4. External Integrations

   Integrate GAME and LyricFA behind their package boundaries. Keep their local
   Python paths and model paths in package config or provenance, not in project
   manifests.

5. Score Export

   Implement canonical score schema models, validation, bar generation, and
   `score.json` export after the mock pipeline is stable.

## Current Non-Goals

- No real separator backend yet.
- No WebUI yet.
- No score renderer yet.
- No Signal bridge implementation yet.
- No heavy audio or ML dependencies in the core environment yet.
