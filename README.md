# Autoscore

Autoscore is a Python 3.12 project for converting vocal audio, lyrics, and
inference outputs into a canonical score timeline and, later, `score.json`.

This repository currently contains the project skeleton, runtime contracts,
development controller/TUI shell, and timeline foundation models. It does not
yet run real audio separation, tempo estimation, GAME inference, LyricFA, or
score export.

## Current Package Layout

```text
autoscore/
  core/
    artifacts/       artifact references
    projects/        project manifest and migration entry point
    problems.py      structured warning/error records

  runtime/
    controller.py    UI-facing orchestration controller
    registry.py      local node registry for development
    tasks.py         task envelope/result contracts

  packages/
    audio/           source separation boundary
    timeline/        tempo, phrase slicing, alignment, stitching
    midi/            GAME integration boundary
    lyric/           LyricFA integration boundary
    score_export/    future score JSON export boundary

  cli/
    main.py          `autoscore` command entrypoint
    tui.py           dependency-free development TUI

tests/
workspaces/          local runtime project data, ignored except `.gitkeep`
```

Private design drafts may exist locally under `.designdocuments/`, but that
directory is intentionally ignored and should not be treated as the current
source of truth.

## Environment

Use `uv`. The project is pinned to Python 3.12 for now:

```toml
requires-python = ">=3.12,<3.13"
```

Install and test:

```powershell
uv sync --extra dev
uv run --extra dev pytest
```

Run CLI/TUI:

```powershell
uv run autoscore projects
uv run autoscore tui
```

For TUI batch project creation, copy `config/autoscore.local.example.json` to
`config/autoscore.local.json`, set `workspaceRoot` to the project workspace
directory, and set `importDir` to the directory where you drop audio files and
optional same-name `.txt` lyric files. Successfully imported files are removed
from `importDir`. The local config file is ignored by Git. In the TUI, press
`c` to create projects from that directory, or `c!` to overwrite an existing
processed project.

## Current Runtime Model

The runtime separates three concepts:

```text
deployment package -> node capability -> task type
```

Current local development node registry:

```text
audio-local          separator-node
timeline-local       tempo-node, phrase-node, alignment-node, stitch-node
midi-local           game-node       unconfigured
lyric-local          lyricfa-node    unconfigured
score-export-local   score-json-node
```

The TUI displays registered nodes even when no task is running. This is a
development visibility feature for checking what the controller knows how to
communicate with.

## Implemented

- Python package skeleton and uv lockfile.
- `ArtifactRef` with local/remote artifact reference fields.
- `ProjectManifest` and `ManifestStep`.
- Project manifest migration entry point.
- Structured `ProblemRecord` warning/error shape.
- `TaskEnvelope`, `TaskResult`, `ExecutionInfo`, and `TaskRequirements`.
- JSON/TOML package config loader.
- Runtime controller and local development node registry.
- Dependency-free CLI/TUI shell.
- CLI project creation and TUI import-directory project creation.
- Local artifact registry and materialization.
- Mock `separateAudio` runner wired through controller/TUI step execution.
- Timeline foundation models:
  - tempo ms/tick conversion;
  - phrase slice metadata;
  - phrase anchor offset;
  - aligned note/lyric fragments;
  - lyric-to-note matching;
  - stitched timeline fragments.

## Not Implemented Yet

- DAG scheduler and rerun/resume behavior.
- Mock runners beyond `separateAudio`.
- Real separator backend.
- Real or mocked tempo/phrase audio analysis.
- Real GAME adapter.
- Real or mocked LyricFA adapter.
- Score schema models and score JSON export.
- WebUI.

## Recommended Next Steps

1. Add timeline mock outputs for `estimateTempo`, `detectPhrases`,
   `alignPhrase`, and `stitchPhrases`.
2. Add mock GAME, LyricFA, and score export task runners.
3. Build an end-to-end mock pipeline before integrating GAME, LyricFA, or
   heavy audio dependencies.
