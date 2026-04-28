# Autoscore Architecture

This document is the current public architecture note for the repository.
Private drafts under `.designdocuments/` are ignored and are not the source of
truth.

## Repository Layout

```text
autoscore/
  core/
    artifacts/       portable artifact references
    projects/        project manifest and migration entry point
    problems.py      structured warning/error records

  runtime/
    controller.py    stable control API for CLI/TUI/future WebUI
    registry.py      local node registry for development
    tasks.py         task envelope/result contracts

  packages/
    audio/           source separation boundary
    timeline/        tempo, phrase slicing, alignment, stitching
    midi/            GAME integration boundary
    lyric/           LyricFA integration boundary
    score_export/    future canonical score JSON export

  cli/
    main.py          `autoscore` command entrypoint
    tui.py           dependency-free development TUI
```

## Runtime Model

Autoscore separates deployable code from node capabilities and task types:

```text
deployment package -> node capability -> task type
```

A deployment package owns one Python/runtime environment by default. Multiple
node capabilities may share that package environment. If one node requires a
conflicting or hardware-specific runtime, split it into its own deployment
package.

Current package boundaries:

```text
audio-package
  separator-node

timeline-package
  tempo-node
  phrase-node
  alignment-node
  stitch-node

midi-package
  game-node

lyric-package
  lyricfa-node

score-export-package
  score-json-node
```

## Controller Boundary

UI layers must call the runtime controller instead of embedding pipeline logic:

```text
CLI / TUI / future WebUI
  -> AutoscoreController
      -> project manifests
      -> node registry
      -> future task runners
```

This keeps the development TUI replaceable by a future WebUI without changing
the orchestration API.

## Local Development Node Registry

The current registry is static and local. It shows which package capabilities
the controller knows about, even when no task is running:

```text
audio-local          separator-node
timeline-local       tempo-node, phrase-node, alignment-node, stitch-node
midi-local           game-node       unconfigured
lyric-local          lyricfa-node    unconfigured
score-export-local   score-json-node
```

Future LAN workers should register through the same conceptual shape: node id,
package id, capabilities, supported tasks, transport, endpoint, status, runtime
metadata, backends, and models.

## Timeline Scope

The timeline package currently contains dependency-free timeline primitives:

- tempo millisecond/tick conversion;
- phrase slice metadata;
- phrase anchor offsets;
- aligned note/lyric fragments;
- lyric-to-note matching;
- stitched song-level timeline fragments.

It does not yet perform real audio analysis. Librosa or Essentia should be added
later behind this package boundary.

## Ignored Local State

The following are intentionally local:

```text
.designdocuments/    private design drafts
.venv/               uv virtual environment
workspaces/*         runtime project data
__pycache__/         Python bytecode cache
```
