"""Autoscore command line entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from autoscore.cli.tui import run_tui
from autoscore.runtime import AutoscoreController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoscore")
    parser.add_argument("--workspace", default="workspaces", help="Workspace root directory.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("projects", help="List projects in the workspace.")

    status_parser = subparsers.add_parser("status", help="Show one project status.")
    status_parser.add_argument("project_id")

    subparsers.add_parser("tui", help="Open the development terminal UI.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    controller = AutoscoreController(Path(args.workspace))

    if args.command == "projects":
        for project in controller.list_projects():
            print(
                f"{project.project_id}\tsteps={project.step_count}\t"
                f"artifacts={project.artifact_count}\twarnings={project.warning_count}\terrors={project.error_count}"
            )
        return 0

    if args.command == "status":
        status = controller.get_project_status(args.project_id)
        print_project_status(status)
        return 0

    if args.command == "tui":
        run_tui(controller)
        return 0

    parser.print_help()
    return 0


def print_project_status(status: object) -> None:
    summary = status.summary
    print(f"Project: {summary.project_id}")
    print(f"Manifest: {summary.manifest_path}")
    print(f"Artifacts: {summary.artifact_count}")
    print(f"Warnings: {summary.warning_count}")
    print(f"Errors: {summary.error_count}")
    print()
    print("Steps:")
    for step in status.steps:
        print(
            f"  {step.task_type:20} {step.status:10} "
            f"in={step.input_artifact_count} out={step.output_artifact_count} "
            f"warn={step.warning_count} err={step.error_count}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
