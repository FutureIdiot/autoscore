"""Worker node registry models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class NodeRegistration:
    """Registered worker/node capability known to the orchestrator."""

    node_id: str
    package_id: str
    capabilities: tuple[str, ...]
    supported_tasks: tuple[str, ...]
    transport: str
    endpoint: str
    status: str = "online"
    last_seen_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id is required")
        if not self.package_id:
            raise ValueError("package_id is required")
        if not self.capabilities:
            raise ValueError("capabilities are required")
        if not self.supported_tasks:
            raise ValueError("supported_tasks are required")
        if not self.transport:
            raise ValueError("transport is required")
        if not self.endpoint:
            raise ValueError("endpoint is required")


def default_local_nodes() -> list[NodeRegistration]:
    """Return static local node registrations for the development runtime."""

    return [
        NodeRegistration(
            node_id="audio-local",
            package_id="audio-package",
            capabilities=("separator-node",),
            supported_tasks=("separateAudio",),
            transport="local",
            endpoint="local://autoscore.packages.audio.separator",
        ),
        NodeRegistration(
            node_id="timeline-local",
            package_id="timeline-package",
            capabilities=("tempo-node", "phrase-node", "alignment-node", "stitch-node"),
            supported_tasks=("estimateTempo", "detectPhrases", "alignPhrase", "stitchPhrases"),
            transport="local",
            endpoint="local://autoscore.packages.timeline",
        ),
        NodeRegistration(
            node_id="midi-local",
            package_id="midi-package",
            capabilities=("game-node",),
            supported_tasks=("smokeTestGame", "runGame"),
            transport="local",
            endpoint="local://autoscore.packages.midi.game",
            status="unconfigured",
            metadata={"externalRuntime": "GAME"},
        ),
        NodeRegistration(
            node_id="lyric-local",
            package_id="lyric-package",
            capabilities=("lyricfa-node",),
            supported_tasks=("runLyricFA",),
            transport="local",
            endpoint="local://autoscore.packages.lyric.lyricfa",
            status="unconfigured",
            metadata={"externalRuntime": "LyricFA"},
        ),
        NodeRegistration(
            node_id="score-export-local",
            package_id="score-export-package",
            capabilities=("score-json-node",),
            supported_tasks=("buildScoreJson",),
            transport="local",
            endpoint="local://autoscore.packages.score_export.score_json",
        ),
    ]
