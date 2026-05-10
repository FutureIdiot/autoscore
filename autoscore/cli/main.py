"""Autoscore command line entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from autoscore.cli.tui import run_tui
from autoscore.runtime import AutoscoreController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoscore")
    parser.add_argument("--workspace", default=None, help="Workspace root directory. Overrides config workspaceRoot.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("projects", help="List projects in the workspace.")

    create_parser = subparsers.add_parser("create", help="Create a project workspace.")
    create_parser.add_argument("--project-id", required=True)
    create_parser.add_argument("--audio", required=True, help="Input audio path.")
    lyrics_source = create_parser.add_mutually_exclusive_group(required=True)
    lyrics_source.add_argument("--lyrics", help="Lyrics text.")
    lyrics_source.add_argument("--lyrics-file", help="Lyrics text file.")
    create_parser.add_argument("--tempo", type=float, default=None, help="Manual global tempo.")
    create_parser.add_argument("--meter", default=None, help="Manual meter as numerator/denominator, for example 4/4.")
    create_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing manifest.")

    status_parser = subparsers.add_parser("status", help="Show one project status.")
    status_parser.add_argument("project_id")

    subparsers.add_parser("tui", help="Open the development terminal UI.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    controller = AutoscoreController(Path(args.workspace) if args.workspace is not None else None)

    if args.command == "projects":
        for project in controller.list_projects():
            print(
                f"{project.project_id}\tsteps={project.step_count}\t"
                f"artifacts={project.artifact_count}\twarnings={project.warning_count}\terrors={project.error_count}"
            )
        return 0

    if args.command == "create":
        manifest = controller.create_project(
            project_id=args.project_id,
            audio_path=args.audio,
            lyrics_text=args.lyrics,
            lyrics_path=args.lyrics_file,
            global_tempo=args.tempo,
            meter=_parse_meter(args.meter) if args.meter else None,
            overwrite=args.overwrite,
        )
        print(f"Created project {manifest.project_id}: {manifest.project_dir}")
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


def _parse_meter(value: str) -> dict[str, int]:
    parts = value.split("/", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("meter must be formatted as numerator/denominator, for example 4/4")
    try:
        numerator = int(parts[0].strip())
        denominator = int(parts[1].strip())
    except ValueError as exc:
        raise ValueError("meter numerator and denominator must be integers") from exc
    if numerator <= 0 or denominator <= 0:
        raise ValueError("meter numerator and denominator must be positive")
    return {"numerator": numerator, "denominator": denominator}


if __name__ == "__main__":
    raise SystemExit(main())
