# Autoscore

Autoscore is a Python 3.12 project for converting vocal audio, lyrics, and
inference outputs into a canonical score timeline and, later, `score.json`.

This repository currently contains the project skeleton, runtime contracts,
development controller/TUI shell, timeline foundation models, and a local mock
pipeline through phrase detection. It does not yet run real audio separation,
tempo estimation, GAME inference, LyricFA, or score export.

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
inbox/               local input drop folder, ignored except `.gitkeep`
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

For TUI project creation, copy `config/autoscore.local.example.json` to
`config/autoscore.local.json`, set `workspaceRoot` to the project workspace
directory, and optionally set `importDir` to the directory where you drop
initial files. If `importDir` is not set, the TUI uses the repository-local
`inbox/` folder.

Initial files are grouped into workspaces by filename prefix:

```text
songname.wav          original/full audio candidate
songname.txt          lyrics candidate
songname_vox.wav      vocals candidate
songname_instrument.wav accompaniment candidate
```

Files with the same prefix create one workspace. The suffix only helps create
grouping; artifact roles are registered later from pending inputs.

Current TUI command shape:

```text
create[!]             create workspaces from inbox/importDir, or an empty workspace when no files exist
info                  view or edit current project tempo and meter
send                  send current project artifacts through the ready mock pipeline
send #                send to the numbered node task shown in the TUI
send #&               send to # and continue through downstream ready tasks
send #!               force rerun #
send TASK             send current artifacts to one named task, e.g. send detectPhrases
```

The `create` command creates project control state first and keeps discovered
files as pending project inputs. Sending to a task is a separate step. Before a
task runs, pending files are registered as artifacts by filename purpose:
names containing `vox` or `vocal` become `artifact_vocals_wav`, names
containing `instrument` or `accompaniment` become `artifact_accompaniment_wav`,
plain audio becomes `artifact_original_audio`, and `.txt` becomes
`artifact_lyrics_txt`.

Task readiness is based on required artifacts only; optional context such as
lyrics, manual metadata, or tempo may be absent and should surface as task
warnings instead of blocking execution. The project `info` command can update
manual tempo and meter after creation. If a task's expected output artifacts
already exist, `send` skips that task and continues downstream; add `!` to force
the task to rerun and overwrite its outputs.

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
- CLI project creation and TUI create/send project workflow.
- Local artifact registry and materialization.
- Artifact-driven task dispatch with required and optional input contracts.
- Pending input binding at send time for task-specific audio artifact roles.
- TUI project info view/edit for manual tempo and meter.
- Empty project creation, pending input registration, provided artifact
  attachment, and provided tempo timeline support.
- Mock `separateAudio`, `estimateTempo`, and `detectPhrases` runners wired
  through controller/TUI send execution.
- Timeline foundation models:
  - tempo ms/tick conversion;
  - phrase slice metadata and mock phrase timeline output;
  - phrase anchor offset;
  - aligned note/lyric fragments;
  - lyric-to-note matching;
  - stitched timeline fragments.

## Not Implemented Yet

- DAG scheduler and rerun/resume behavior.
- Mock runners beyond `separateAudio`, `estimateTempo`, and `detectPhrases`.
- Real separator backend.
- Real tempo/phrase audio analysis.
- Real GAME adapter.
- Real or mocked LyricFA adapter.
- Score schema models and score JSON export.
- WebUI.

## Next Steps

1. Add mock outputs for `runGame`, `runLyricFA`, `alignPhrase`,
   `stitchPhrases`, and `buildScoreJson`.
2. Build an end-to-end mock pipeline before integrating GAME, LyricFA, or
   heavy audio dependencies.
3. Add clearer rerun/resume behavior once more downstream steps exist.
