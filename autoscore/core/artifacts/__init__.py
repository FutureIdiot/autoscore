"""Artifact reference models."""

from autoscore.core.artifacts.refs import ArtifactRef
from autoscore.core.artifacts.store import (
    LocalArtifactStore,
    artifact_id_from_path,
    default_extension_for_kind,
    file_sha256,
)

__all__ = [
    "ArtifactRef",
    "LocalArtifactStore",
    "artifact_id_from_path",
    "default_extension_for_kind",
    "file_sha256",
]
