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
    midi/            MIDI import and analysis boundary
    lyric/           lyric import and analysis boundary
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
  midi-analysis-node

lyric-package
  lyric-analysis-node

score-export-package
  score-json-node
```

## Node Registry and Task Mapping

Remote node control should use the same three-level mapping as the local
development registry:

```text
deployment package -> node capability -> task type
```

This mapping is a protocol boundary, not only a TUI display detail. Registry
records must be serializable so a controller can load local JSON/TOML config
today and later accept remote worker registration messages with the same shape.

A serialized node registration should preserve these stable fields:

```json
{
  "nodeId": "timeline-local",
  "packageId": "timeline-package",
  "packageVersion": "0.1.0",
  "capabilities": ["tempo-node", "phrase-node"],
  "supportedTasks": ["estimateTempo", "detectPhrases"],
  "transport": "local",
  "endpoint": "local://autoscore.packages.timeline",
  "status": "online",
  "lastSeenAt": null,
  "schemaVersions": [1],
  "artifactKinds": ["audio/wav", "text/plain", "application/json"],
  "runtime": {"python": "3.12"},
  "backends": {"mock": true},
  "models": {},
  "metadata": {}
}
```

Deserialization should rebuild controller-visible `NodeRegistration` records
and keep enough package metadata to answer three scheduling questions:

1. Which task type did the user or scheduler request?
2. Which node capabilities can execute that task type?
3. Which deployment package, transport, and endpoint should receive the task
   envelope?

The task type remains the command-level unit. Required and optional artifact
contracts belong to task definitions, not to project manifests. When the TUI
resolves `send 2` or `send detectPhrases`, the controller maps that target to a
task type, checks the task artifact contract, binds any pending input needed by
that task, and then builds a `TaskEnvelope` for a node that supports the task.

Project manifests should store durable project state: artifacts, steps, manual
metadata, warnings, and errors. They should not store machine-specific runtime
details such as absolute model paths, temporary worker process state, local
cache paths, or live health-check results. Those belong in deployment config,
node registry records, heartbeat state, or execution provenance attached to an
individual step.

Future remote registries should add live health signals without changing the
core mapping shape:

- heartbeat timestamp and timeout policy;
- accepted schema versions;
- supported artifact transports;
- supported backends and model variants;
- current status such as `online`, `degraded`, `busy`, `offline`, or
  `unconfigured`.

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
midi-local           midi-analysis-node unconfigured
lyric-local          lyric-analysis-node unconfigured
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

## External MIDI Generation

Autoscore core treats MIDI generation as an external tool step. Users may use
GAME, a DAW, or another MIDI extraction tool, then provide the resulting MIDI to
the pipeline for import and analysis. This keeps packaged Autoscore builds free
from GAME runtime and licensing constraints while still allowing GAME-centered
local workflows.

## External Lyric Alignment

Autoscore core treats lyric forced alignment the same way. Users may run
LyricFA or another alignment tool outside the core package, then provide lyric
timing data for import and analysis. The default package boundary remains a
neutral lyric analysis node so packaged builds do not inherit external tool
runtime or licensing constraints.

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
