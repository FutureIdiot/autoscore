"""Project manifest migration helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from autoscore.constants import SCHEMA_VERSION


def migrate_manifest_dict(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return manifest data compatible with the current schema version.

    Stage 1 only has schema version 1, so this function records version
    mismatches without attempting lossy conversion. Future migrations should
    convert older versions here before ProjectManifest is constructed.
    """

    migrated = deepcopy(data)
    source_version = migrated.get("schemaVersion", SCHEMA_VERSION)
    warnings: list[str] = []

    if source_version != SCHEMA_VERSION:
        warnings.append(
            f"manifest schemaVersion {source_version} differs from current {SCHEMA_VERSION}; "
            "no automatic migration is available yet"
        )

    migrated.setdefault("schemaVersion", source_version)
    existing_warnings = list(migrated.get("warnings", []))
    migrated["warnings"] = existing_warnings + warnings
    return migrated, warnings
