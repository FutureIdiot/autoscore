"""Load local package configuration files."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autoscore.constants import SCHEMA_VERSION


@dataclass(slots=True)
class AppConfig:
    """Local application configuration for development control surfaces."""

    workspace_root: str = "workspaces"
    import_dir: str | None = None
    default_tempo: float | None = None
    audio_extensions: list[str] = field(default_factory=lambda: [".wav", ".flac", ".mp3", ".m4a"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            workspace_root=data.get("workspaceRoot", "workspaces"),
            import_dir=data.get("importDir"),
            default_tempo=data.get("defaultTempo"),
            audio_extensions=[str(item).lower() for item in data.get("audioExtensions", [".wav", ".flac", ".mp3", ".m4a"])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspaceRoot": self.workspace_root,
            "importDir": self.import_dir,
            "defaultTempo": self.default_tempo,
            "audioExtensions": self.audio_extensions,
        }


@dataclass(slots=True)
class PackageConfig:
    """Local deployment package configuration."""

    package_id: str
    package_version: str
    node_id: str
    node_types: list[str]
    supported_tasks: list[str]
    schema_versions: list[int] = field(default_factory=lambda: [SCHEMA_VERSION])
    artifact_kinds: list[str] = field(default_factory=list)
    local_artifact_cache_dir: str | None = None
    runtime: dict[str, Any] = field(default_factory=dict)
    backends: dict[str, Any] = field(default_factory=dict)
    models: dict[str, Any] = field(default_factory=dict)
    paths: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.package_id:
            raise ValueError("package_id is required")
        if not self.package_version:
            raise ValueError("package_version is required")
        if not self.node_id:
            raise ValueError("node_id is required")
        if not self.node_types:
            raise ValueError("node_types are required")
        if not self.supported_tasks:
            raise ValueError("supported_tasks are required")
        if SCHEMA_VERSION not in self.schema_versions:
            raise ValueError(f"schema_versions must include current schema version {SCHEMA_VERSION}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackageConfig":
        return cls(
            package_id=data["packageId"],
            package_version=data["packageVersion"],
            node_id=data["nodeId"],
            node_types=list(data["nodeTypes"]),
            supported_tasks=list(data["supportedTasks"]),
            schema_versions=[int(item) for item in data.get("schemaVersions", [SCHEMA_VERSION])],
            artifact_kinds=list(data.get("artifactKinds", [])),
            local_artifact_cache_dir=data.get("localArtifactCacheDir"),
            runtime=dict(data.get("runtime", {})),
            backends=dict(data.get("backends", {})),
            models=dict(data.get("models", {})),
            paths=dict(data.get("paths", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "packageId": self.package_id,
            "packageVersion": self.package_version,
            "nodeId": self.node_id,
            "nodeTypes": self.node_types,
            "supportedTasks": self.supported_tasks,
            "schemaVersions": self.schema_versions,
            "artifactKinds": self.artifact_kinds,
            "localArtifactCacheDir": self.local_artifact_cache_dir,
            "runtime": self.runtime,
            "backends": self.backends,
            "models": self.models,
            "paths": self.paths,
        }


def load_package_config(path: str | Path) -> PackageConfig:
    """Load a package config from JSON or TOML."""

    config_path = Path(path)
    if config_path.suffix.lower() == ".json":
        with config_path.open("r", encoding="utf-8") as handle:
            return PackageConfig.from_dict(json.load(handle))
    if config_path.suffix.lower() == ".toml":
        with config_path.open("rb") as handle:
            return PackageConfig.from_dict(tomllib.load(handle))
    raise ValueError(f"unsupported package config format: {config_path.suffix}")


def load_app_config(path: str | Path = "config/autoscore.local.json") -> AppConfig:
    """Load local app config, returning defaults when no file exists."""

    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    if config_path.suffix.lower() == ".json":
        with config_path.open("r", encoding="utf-8") as handle:
            return AppConfig.from_dict(json.load(handle))
    if config_path.suffix.lower() == ".toml":
        with config_path.open("rb") as handle:
            return AppConfig.from_dict(tomllib.load(handle))
    raise ValueError(f"unsupported app config format: {config_path.suffix}")
