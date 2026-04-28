"""Redeployable worker package implementations.

The runtime model is:

deployment package -> node capability -> task type

These Python packages mirror deployment packages, not individual tasks.
Each package may expose one or more node capabilities under its ``nodes``
module.

Environment rule: one deployment package owns one Python/runtime environment by
default. If a node requires a highly specialized or conflicting environment,
split that node into its own deployment package instead of giving one package
multiple hidden environments.
"""
