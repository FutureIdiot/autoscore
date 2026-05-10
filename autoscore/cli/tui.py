"""Small dependency-free development TUI."""

from __future__ import annotations

from pathlib import Path

from autoscore.runtime import AutoscoreController, ProjectStatus, project_id_from_name


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
            "Project #, create[!], [h] help, [r] refresh, [q] quit: "
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
        if not choice.isdigit() or not 1 <= int(choice) <= len(projects):
            continue
        _project_screen(controller, projects[int(choice) - 1].project_id)


def _project_screen(controller: AutoscoreController, project_id: str) -> None:
    while True:
        status = controller.get_project_status(project_id)
        _clear_screen()
        _print_project_status(status)
        print()
        choice = _prompt(
            "send [task][&][!], [h] help, [b] back, [q] quit: "
        ).strip()
        normalized = choice.lower()
        if normalized == "b":
            return
        if normalized == "q":
            raise SystemExit(0)
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
        task_type, continue_pipeline, force = _parse_send_command(command)
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


def _parse_send_command(command: str) -> tuple[str | None, bool, bool]:
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
    task_type = payload or None
    if task_type is None:
        continue_pipeline = True
    return task_type, continue_pipeline, force


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
        audio_files = _audio_files_from_inbox(controller)
        manifests = []
        if audio_files:
            print()
            print("Detected audio files:")
            for audio_file in audio_files:
                print(f"- {audio_file.name}")
            for audio_path in audio_files:
                manifests.append(
                    _create_project_for_audio_file(
                        controller,
                        audio_path=audio_path,
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


def _create_project_for_audio_file(
    controller: AutoscoreController,
    *,
    audio_path: Path,
    tempo: float | None,
    meter: dict[str, int] | None,
    overwrite: bool,
):
    project_id = project_id_from_name(audio_path.stem)
    if _looks_like_vocals(audio_path):
        return controller.create_project_from_provided_vocals(
            project_id=project_id,
            vocals_path=audio_path,
            global_tempo=tempo,
            meter=meter,
            overwrite=overwrite,
        )
    lyrics_path = audio_path.with_suffix(".txt")
    manifest = controller.create_project(
        project_id=project_id,
        audio_path=audio_path,
        lyrics_path=lyrics_path if lyrics_path.exists() else None,
        lyrics_text="" if not lyrics_path.exists() else None,
        global_tempo=tempo,
        meter=meter,
        overwrite=overwrite,
    )
    controller.attach_artifact(
        manifest.project_id,
        source_path=audio_path,
        artifact_id="artifact_vocals_wav",
        kind="audio/wav",
        relative_path="audio/vocals.wav",
        metadata={"providedAs": "vocalsCandidate"},
    )
    return controller.provide_tempo_timeline(manifest.project_id, global_tempo=tempo)


def _prompt_send_after_create(controller: AutoscoreController, manifests: list[object]) -> None:
    command = _prompt("Send now? Enter=full pipeline, task/[task&]/[task!] or n=skip: ").strip()
    if command.lower() in {"n", "no"}:
        return
    send_command = "send" if not command else f"send {command}"
    for manifest in manifests:
        _send_to_nodes(controller, manifest.project_id, send_command, pause=False)


def _looks_like_vocals(audio_path: Path) -> bool:
    normalized = audio_path.stem.lower().replace("-", "_").replace(" ", "_")
    return "vocal" in normalized or "vocals" in normalized


def _print_help() -> None:
    print()
    print("Commands")
    print("--------")
    print("create     Create a project from an inbox/import-dir audio file.")
    print("create!    Create and overwrite an existing project.")
    print("send       In a project, start at the first ready pipeline node and continue.")
    print("send TASK  Send current artifacts to one task only, e.g. send detectPhrases.")
    print("send TASK& Send to TASK, then continue through downstream ready nodes.")
    print("send TASK! Force rerun TASK.")
    print("send TASK&! Force rerun from TASK, then continue downstream.")
    print("r          Refresh.")
    print("b          Go back from a project.")
    print("q          Quit.")
    _prompt("Press Enter to continue: ")


def _create_from_import_dir(controller: AutoscoreController, *, overwrite: bool = False) -> None:
    _clear_screen()
    print("Create Projects From Import Directory")
    print("-------------------------------------")
    print(f"Configured import dir: {controller.app_config.import_dir or '(not configured)'}")
    print(f"Default tempo: {controller.app_config.default_tempo}")
    print(f"Overwrite existing projects: {overwrite}")
    print()
    tempo = _prompt_optional_float(
        "Manual tempo BPM (blank=use configured default/auto): ",
        field_name="tempo",
    )
    meter = _prompt_meter("Meter, e.g. 4/4 (blank=4/4 later): ")
    print()
    try:
        results = controller.create_projects_from_import_dir(
            default_tempo=tempo,
            meter=meter,
            overwrite=overwrite,
        )
    except Exception as exc:
        print(f"Failed: {exc}")
        _prompt("Press Enter to continue: ")
        return
    if not results:
        print("No audio files found.")
    for result in results:
        line = f"{result.status:8} {result.project_id} <- {result.audio_path}"
        if result.message:
            line += f" ({result.message})"
        print(line)
    _prompt("Press Enter to continue: ")


def _create_from_provided_vocals(controller: AutoscoreController, *, overwrite: bool = False) -> None:
    _clear_screen()
    print("Create Project From Provided Vocals")
    print("-----------------------------------")
    print(f"Inbox/import dir: {_provided_audio_inbox(controller)}")
    print(f"Overwrite existing projects: {overwrite}")
    print()
    try:
        vocals_path = _select_audio_file_from_import_dir(controller)
        if vocals_path is None:
            print("No vocals file selected.")
            _prompt("Press Enter to continue: ")
            return
        default_project_id = project_id_from_name(vocals_path.stem)
        project_id = _prompt(f"Project id (blank={default_project_id}): ").strip() or default_project_id
        tempo = _prompt_optional_float(
            "Manual tempo BPM (blank=120 mock default): ",
            field_name="tempo",
        )
        meter = _prompt_meter("Meter, e.g. 4/4 (blank=4/4 later): ")
        manifest = controller.create_project_from_provided_vocals(
            project_id=project_id,
            vocals_path=vocals_path,
            global_tempo=tempo,
            meter=meter,
            overwrite=overwrite,
        )
        result = controller.run_step(manifest.project_id, "detectPhrases")
    except Exception as exc:
        print(f"Failed: {exc}")
    else:
        print(f"Created {manifest.project_id} from provided vocals.")
        print(f"{result.task_type}: {result.status}")
    _prompt("Press Enter to continue: ")


def _select_audio_file_from_import_dir(controller: AutoscoreController) -> Path | None:
    audio_files = _audio_files_from_inbox(controller)
    if not audio_files:
        print("No audio files found.")
        return None
    for index, audio_file in enumerate(audio_files, start=1):
        print(f"{index}. {audio_file.name}")
    choice = _prompt("Select vocals file number, or blank=cancel: ").strip()
    if not choice:
        return None
    if not choice.isdigit() or not 1 <= int(choice) <= len(audio_files):
        raise ValueError("invalid audio file selection")
    return audio_files[int(choice) - 1]


def _audio_files_from_inbox(controller: AutoscoreController) -> list[Path]:
    root = _provided_audio_inbox(controller)
    if not root.is_dir():
        raise FileNotFoundError(root)
    audio_extensions = {extension.lower() for extension in controller.app_config.audio_extensions}
    return sorted(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in audio_extensions)


def _provided_audio_inbox(controller: AutoscoreController) -> Path:
    return Path(controller.app_config.import_dir or "inbox")


def _print_nodes(controller: AutoscoreController) -> None:
    print("Deployed Nodes")
    print("--------------")
    nodes = controller.list_nodes()
    if not nodes:
        print("(no registered nodes)")
        return
    for node in nodes:
        capabilities = ", ".join(node.capabilities)
        tasks = ", ".join(node.supported_tasks)
        print(f"{node.node_id} [{node.status}]")
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
    print()
    print("Ready Nodes")
    print("-----------")
    ready_tasks = [task for task in status.task_readiness if task.ready and task.status != "succeeded"]
    if not ready_tasks:
        print("(none)")
    for task in ready_tasks:
        print(f"{task.node_id:18} <- {task.task_type}")


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
