"""Small dependency-free development TUI."""

from __future__ import annotations

from pathlib import Path

from autoscore.runtime import AutoscoreController, ProjectStatus, input_group_name_from_path, project_id_from_name


def run_tui(controller: AutoscoreController) -> None:
    """Run a minimal terminal UI for development inspection."""

    while True:
        projects = controller.list_projects()
        _clear_screen()
        print("Autoscore Development TUI")
        print("=========================")
        _print_nodes(controller)
        print()
        if not projects:
            print("No projects found under workspace.")
            print()
            choice = _prompt(
                "create[!]  [h] help  [q] quit  Enter=refresh: "
            ).lower()
            if choice == "q":
                return
            if choice == "h":
                _print_help()
                continue
            if choice in {"create", "create!"}:
                _create_project(controller, overwrite=choice.endswith("!"))
            continue

        for index, project in enumerate(projects, start=1):
            print(
                f"{index}. {project.project_id} "
                f"steps={project.step_count} artifacts={project.artifact_count} "
                f"warnings={project.warning_count} errors={project.error_count}"
            )
        print()
        choice = _prompt(
            "Project #/name, create[!], [h] help, [r] refresh, [q] quit: "
        ).strip().lower()
        if choice == "q":
            return
        if choice == "h":
            _print_help()
            continue
        if choice in {"create", "create!"}:
            _create_project(controller, overwrite=choice.endswith("!"))
            continue
        if choice in {"", "r"}:
            continue
        project_id = _parse_project_selection(choice, project_ids=[project.project_id for project in projects])
        if project_id is None:
            continue
        _project_screen(controller, project_id)


def _project_screen(controller: AutoscoreController, project_id: str) -> None:
    while True:
        status = controller.get_project_status(project_id)
        _clear_screen()
        _print_nodes(controller, status=status)
        print()
        _print_project_status(status)
        print()
        choice = _prompt(
            "send [#|task][&][!], [i] info, [h] help, [b] back, [q] quit: "
        ).strip()
        normalized = choice.lower()
        if normalized == "b":
            return
        if normalized == "q":
            raise SystemExit(0)
        if normalized in {"i", "info"}:
            _project_info_screen(controller, project_id)
            continue
        if normalized == "h":
            _print_help()
            continue
        if normalized in {"", "r"}:
            continue
        if normalized.startswith("send "):
            _send_to_nodes(controller, project_id, choice)
            continue
        if normalized == "send" or normalized in {"send&", "send!"} or normalized == "send&!":
            _send_to_nodes(controller, project_id, choice)


def _parse_project_selection(choice: str, *, project_ids: list[str]) -> str | None:
    normalized = choice.strip().lower()
    if normalized.startswith("project "):
        normalized = normalized.removeprefix("project ").strip()
    if normalized.startswith("#"):
        normalized = normalized[1:].strip()
    if normalized.isdigit():
        index = int(normalized)
        if 1 <= index <= len(project_ids):
            return project_ids[index - 1]
        return None
    for project_id in project_ids:
        if normalized == project_id.lower():
            return project_id
    return None


def _run_step(controller: AutoscoreController, project_id: str, task_type: str) -> None:
    try:
        result = controller.run_step(project_id, task_type)
    except Exception as exc:
        print(f"Failed: {exc}")
    else:
        print(f"{result.task_type}: {result.status}")
    _prompt("Press Enter to continue: ")


def _send_to_nodes(controller: AutoscoreController, project_id: str, command: str, *, pause: bool = True) -> None:
    try:
        task_type, continue_pipeline, force = _parse_send_command(
            command,
            status=controller.get_project_status(project_id),
        )
        _prepare_task_context(controller, project_id, task_type)
        results = controller.send_to_task(
            project_id,
            task_type=task_type,
            continue_pipeline=continue_pipeline,
            force=force,
        )
    except Exception as exc:
        print(f"Failed: {exc}")
    else:
        if not results:
            print("No ready nodes.")
        for result in results:
            print(f"{result.execution.node_id}: {result.task_type} -> {result.status}")
    if pause:
        _prompt("Press Enter to continue: ")


def _prepare_task_context(controller: AutoscoreController, project_id: str, task_type: str | None) -> None:
    if task_type != "detectPhrases":
        return
    status = controller.get_project_status(project_id)
    if "artifact_tempo_timeline_json" in status.artifact_ids:
        return
    tempo = _prompt_optional_float(
        "Tempo BPM for detectPhrases (blank=120 default): ",
        field_name="tempo",
    )
    controller.provide_tempo_timeline(project_id, global_tempo=tempo)


def _parse_send_command(command: str, *, status: ProjectStatus | None = None) -> tuple[str | None, bool, bool]:
    payload = command.strip()[len("send") :].strip()
    continue_pipeline = False
    force = False
    while payload.endswith(("!", "&")):
        suffix = payload[-1]
        payload = payload[:-1].strip()
        if suffix == "!":
            force = True
        if suffix == "&":
            continue_pipeline = True
    task_type = _task_type_from_send_payload(payload, status=status) if payload else None
    if task_type is None:
        continue_pipeline = True
    return task_type, continue_pipeline, force


def _task_type_from_send_payload(payload: str, *, status: ProjectStatus | None) -> str:
    normalized = payload.strip()
    if normalized.startswith("#"):
        normalized = normalized[1:].strip()
    if normalized.isdigit():
        if status is None:
            raise ValueError("send target numbers require a project status")
        index = int(normalized)
        if not 1 <= index <= len(status.task_readiness):
            raise ValueError(f"send target #{index} is out of range")
        return status.task_readiness[index - 1].task_type
    if status is not None:
        for task in status.task_readiness:
            if normalized.lower() in {task.task_type.lower(), task.node_id.lower()}:
                return task.task_type
    return normalized


def _project_info_screen(controller: AutoscoreController, project_id: str) -> None:
    _clear_screen()
    print("Project Info")
    print("------------")
    manifest = controller.load_manifest(project_id)
    manual = dict(manifest.metadata.get("manual", {}))
    tempo = manual.get("globalTempo")
    meter = manual.get("meter") if isinstance(manual.get("meter"), dict) else {}
    print(f"Project: {manifest.project_id}")
    print(f"Directory: {manifest.project_dir}")
    print(f"Tempo BPM: {_format_optional_value(tempo)}")
    print(f"Meter: {_format_meter(meter)}")
    print()
    choice = _prompt("Edit manual parameters? [y/N]: ").strip().lower()
    if choice not in {"y", "yes"}:
        return
    new_tempo = _prompt_optional_float(
        f"Tempo BPM (blank=keep {_format_optional_value(tempo)}): ",
        field_name="tempo",
    )
    if new_tempo is None:
        new_tempo = float(tempo) if isinstance(tempo, int | float) else None
    new_meter = _prompt_meter(f"Meter (blank=keep {_format_meter(meter)}): ")
    if new_meter is None:
        new_meter = meter if meter else None
    controller.update_manual_project_info(project_id, global_tempo=new_tempo, meter=new_meter)
    print("Updated project info.")
    _prompt("Press Enter to continue: ")


def _create_project(controller: AutoscoreController, *, overwrite: bool = False) -> None:
    _clear_screen()
    print("Create Project")
    print("--------------")
    print(f"Inbox/import dir: {_provided_audio_inbox(controller)}")
    print(f"Overwrite existing projects: {overwrite}")
    print()
    try:
        tempo = _prompt_optional_float(
            "Manual tempo BPM (blank=use default/auto): ",
            field_name="tempo",
        )
        meter = _prompt_meter("Meter, e.g. 4/4 (blank=4/4 later): ")
        input_groups = _input_groups_from_inbox(controller)
        manifests = []
        if input_groups:
            print()
            print("Detected input groups:")
            for group_name, input_files in input_groups:
                filenames = ", ".join(path.name for path in input_files)
                print(f"- {group_name}: {filenames}")
            for group_name, input_files in input_groups:
                manifests.append(
                    _create_project_for_input_group(
                        controller,
                        group_name=group_name,
                        input_files=input_files,
                        tempo=tempo,
                        meter=meter,
                        overwrite=overwrite,
                    )
                )
        else:
            print("No audio files found. Creating an empty project.")
            project_id = _prompt("Project id: ").strip()
            if not project_id:
                print("Cancelled.")
                _prompt("Press Enter to continue: ")
                return
            manifests.append(controller.create_empty_project(project_id=project_id, overwrite=overwrite))
    except Exception as exc:
        print(f"Failed: {exc}")
    else:
        for manifest in manifests:
            print(f"Created {manifest.project_id}.")
        _prompt_send_after_create(controller, manifests)
    _prompt("Press Enter to continue: ")


def _create_project_for_input_group(
    controller: AutoscoreController,
    *,
    group_name: str,
    input_files: list[Path],
    tempo: float | None,
    meter: dict[str, int] | None,
    overwrite: bool,
):
    project_id = project_id_from_name(group_name)
    manifest = controller.create_project_from_pending_inputs(
        project_id=project_id,
        input_paths=input_files,
        overwrite=overwrite,
    )
    manifest.metadata["manual"] = {
        "globalTempo": tempo,
        "meter": meter or {},
        "key": {},
    }
    manifest.save(Path(manifest.project_dir) / "manifest.json")
    return manifest


def _prompt_send_after_create(controller: AutoscoreController, manifests: list[object]) -> None:
    command = _prompt("Send now? Enter=full pipeline, task/[task&]/[task!] or n=skip: ").strip()
    if command.lower() in {"n", "no"}:
        return
    send_command = "send" if not command else f"send {command}"
    for manifest in manifests:
        _send_to_nodes(controller, manifest.project_id, send_command, pause=False)


def _print_help() -> None:
    print()
    print("Commands")
    print("--------")
    print("create     Create a project from an inbox/import-dir audio file.")
    print("create!    Create and overwrite an existing project.")
    print("info       View or edit current project tempo and meter.")
    print("send       In a project, start at the first ready pipeline node and continue.")
    print("send #     Send to a numbered node task, e.g. send 2.")
    print("send TASK  Send to a named task, e.g. send detectPhrases.")
    print("send #&    Send to #, then continue through downstream ready nodes.")
    print("send #!    Force rerun #.")
    print("r          Refresh.")
    print("b          Go back from a project.")
    print("q          Quit.")
    _prompt("Press Enter to continue: ")


def _input_groups_from_inbox(controller: AutoscoreController) -> list[tuple[str, list[Path]]]:
    root = _provided_audio_inbox(controller)
    if not root.is_dir():
        raise FileNotFoundError(root)
    input_extensions = {extension.lower() for extension in controller.app_config.audio_extensions}
    input_extensions.add(".txt")
    grouped: dict[str, list[Path]] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in input_extensions:
            continue
        grouped.setdefault(input_group_name_from_path(path), []).append(path)
    return sorted(grouped.items(), key=lambda item: project_id_from_name(item[0]).lower())


def _provided_audio_inbox(controller: AutoscoreController) -> Path:
    return Path(controller.app_config.import_dir or "inbox")


def _print_nodes(controller: AutoscoreController, *, status: ProjectStatus | None = None) -> None:
    print("Deployed Nodes")
    print("--------------")
    if status is not None:
        if not status.task_readiness:
            print("(no runnable node tasks)")
            return
        for index, task in enumerate(status.task_readiness, start=1):
            marker = "ready" if task.ready else "pending"
            print(f"{index}. {task.node_id:18} <- {task.task_type:16} {marker:7} step={task.status}")
        return
    nodes = controller.list_nodes()
    if not nodes:
        print("(no registered nodes)")
        return
    for index, node in enumerate(nodes, start=1):
        capabilities = ", ".join(node.capabilities)
        tasks = ", ".join(node.supported_tasks)
        print(f"{index}. {node.node_id} [{node.status}]")
        print(f"  package: {node.package_id}")
        print(f"  capabilities: {capabilities}")
        print(f"  tasks: {tasks}")
        print(f"  endpoint: {node.transport} {node.endpoint}")


def _print_project_status(status: ProjectStatus) -> None:
    summary = status.summary
    print(f"Project: {summary.project_id}")
    print(f"Manifest: {summary.manifest_path}")
    print()
    print("Steps")
    print("-----")
    if not status.steps:
        print("(no steps)")
    for step in status.steps:
        node = step.execution_node_id or "-"
        print(
            f"{step.task_type:20} {step.status:10} "
            f"node={node:14} "
            f"in={step.input_artifact_count} out={step.output_artifact_count} "
            f"warn={step.warning_count} err={step.error_count}"
        )
    print()
    print("Artifacts")
    print("---------")
    if not status.artifact_ids:
        print("(no artifacts)")
    for artifact_id in status.artifact_ids:
        print(f"- {artifact_id}")
    if status.warnings or status.errors:
        print()
        print("Messages")
        print("--------")
        for warning in status.warnings:
            print(f"WARN: {warning}")
        for error in status.errors:
            print(f"ERR: {error}")


def _format_optional_value(value: object) -> str:
    return "unset" if value is None else str(value)


def _format_meter(value: object) -> str:
    if not isinstance(value, dict):
        return "unset"
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if numerator is None or denominator is None:
        return "unset"
    return f"{numerator}/{denominator}"


def _prompt(text: str) -> str:
    try:
        return input(text)
    except EOFError:
        return "q"


def _prompt_optional_float(text: str, *, field_name: str) -> float | None:
    while True:
        value = _prompt(text).strip()
        if not value or value.lower() == "q":
            return None
        try:
            parsed = float(value)
        except ValueError:
            print(f"Invalid {field_name}: expected a number.")
            continue
        if parsed <= 0:
            print(f"Invalid {field_name}: expected a positive number.")
            continue
        return parsed


def _prompt_meter(text: str) -> dict[str, int] | None:
    while True:
        value = _prompt(text).strip()
        if not value or value.lower() == "q":
            return None
        parts = value.split("/", maxsplit=1)
        if len(parts) != 2:
            print("Invalid meter: expected numerator/denominator, for example 4/4.")
            continue
        try:
            numerator = int(parts[0].strip())
            denominator = int(parts[1].strip())
        except ValueError:
            print("Invalid meter: numerator and denominator must be integers.")
            continue
        if numerator <= 0 or denominator <= 0:
            print("Invalid meter: numerator and denominator must be positive.")
            continue
        return {"numerator": numerator, "denominator": denominator}


def _clear_screen() -> None:
    print("\n" * 3)
