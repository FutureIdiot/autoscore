"""Shared version constants for Autoscore wire and persistence contracts."""

PROJECT_MANIFEST_SCHEMA_VERSION = 1
PACKAGE_CONFIG_SCHEMA_VERSION = 1
TASK_REQUIREMENTS_SCHEMA_VERSION = 1
TASK_ENVELOPE_SCHEMA_VERSION = 1

# Backward-compatible alias for older imports. The generic name refers to the
# project manifest schema, which was the first persisted schema in the project.
SCHEMA_VERSION = PROJECT_MANIFEST_SCHEMA_VERSION
