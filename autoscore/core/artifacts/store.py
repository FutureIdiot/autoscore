"""Local artifact store for project workspaces."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath

from autoscore.core.artifacts.refs import ArtifactRef

_ARTIFACT_ID_SAFE_CHARS = re.compile(r"[^a-z0-9]+")
_KIND_EXTENSION = {
    "audio/wav": ".wav",
    "audio/flac": ".flac",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/midi": ".mid",
    "text/plain": ".txt",
    "application/json": ".json",
}


class LocalArtifactStore:
    """Stores artifacts under one project workspace."""

    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir)

    def artifact_path(self, ref: ArtifactRef) -> Path:
        """Return the local path for an artifact reference."""

        if not ref.relative_path:
            raise ValueError("artifact has no relative_path")
        return self.resolve_relative_path(ref.relative_path)

    def resolve_relative_path(self, relative_path: str) -> Path:
        """Resolve a project-relative path and reject path traversal."""

        if _is_absolute_path(relative_path):
            raise ValueError("relative_path must not be absolute")
        normalized = PurePosixPath(relative_path.replace("\\", "/"))
        if any(part == ".." for part in normalized.parts):
            raise ValueError("relative_path must not contain '..'")
        return self.project_dir / Path(*normalized.parts)

    def create_ref(
        self,
        *,
        artifact_id: str,
        kind: str,
        relative_path: str,
        metadata: dict[str, object] | None = None,
    ) -> ArtifactRef:
        """Create an ArtifactRef for an existing file in the project."""

        path = self.resolve_relative_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        return ArtifactRef(
            artifact_id=artifact_id,
            kind=kind,
            relative_path=relative_path,
            sha256=file_sha256(path),
            size_bytes=path.stat().st_size,
            metadata=dict(metadata or {}),
        )

    def import_file(
        self,
        source_path: str | Path,
        *,
        kind: str,
        relative_path: str,
        artifact_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ArtifactRef:
        """Copy a source file into the project and return its ArtifactRef."""

        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        target = self.resolve_relative_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return self.create_ref(
            artifact_id=artifact_id or artifact_id_from_path(relative_path, kind=kind),
            kind=kind,
            relative_path=relative_path,
            metadata=metadata,
        )

    def materialize(self, ref: ArtifactRef) -> Path:
        """Return a local path for an artifact and verify it exists."""

        path = self.artifact_path(ref)
        if not path.is_file():
            raise FileNotFoundError(path)
        if ref.sha256 and file_sha256(path) != ref.sha256:
            raise ValueError(f"artifact hash mismatch: {ref.artifact_id}")
        if ref.size_bytes is not None and path.stat().st_size != ref.size_bytes:
            raise ValueError(f"artifact size mismatch: {ref.artifact_id}")
        return path


def artifact_id_from_path(relative_path: str, *, kind: str | None = None) -> str:
    """Generate a stable artifact id from a project-relative path."""

    path = PurePosixPath(relative_path.replace("\\", "/"))
    stem = path.with_suffix("").as_posix()
    base = _ARTIFACT_ID_SAFE_CHARS.sub("_", stem.lower()).strip("_")
    if not base:
        raise ValueError("relative_path must contain a usable name")
    suffix = ""
    if kind:
        suffix = _ARTIFACT_ID_SAFE_CHARS.sub("_", kind.lower()).strip("_")
    return f"artifact_{base}{'_' + suffix if suffix else ''}"


def default_extension_for_kind(kind: str) -> str | None:
    return _KIND_EXTENSION.get(kind)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_absolute_path(path: str) -> bool:
    return PureWindowsPath(path).is_absolute() or PurePosixPath(path).is_absolute()
