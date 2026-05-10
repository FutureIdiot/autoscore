"""Small dependency-free development TUI."""

from __future__ import annotations

from autoscore.runtime import AutoscoreController, ProjectStatus


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
            choice = _prompt("c=create from import dir, c!=force overwrite, q=quit, Enter=refresh: ").lower()
            if choice == "q":
                return
            if choice in {"c", "c!"}:
                _create_from_import_dir(controller, overwrite=choice.endswith("!"))
            continue

        for index, project in enumerate(projects, start=1):
            print(
                f"{index}. {project.project_id} "
                f"steps={project.step_count} artifacts={project.artifact_count} "
                f"warnings={project.warning_count} errors={project.error_count}"
            )
        print()
        choice = _prompt("Select project number, c=create from import dir, c!=force overwrite, r=refresh, q=quit: ").strip().lower()
        if choice == "q":
            return
        if choice in {"c", "c!"}:
            _create_from_import_dir(controller, overwrite=choice.endswith("!"))
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
        choice = _prompt("s=run separateAudio, t=run estimateTempo, run <task>, b=back, r=refresh, q=quit: ").strip()
        normalized = choice.lower()
        if normalized == "b":
            return
        if normalized == "q":
            raise SystemExit(0)
        if normalized in {"", "r"}:
            continue
        if normalized == "s":
            _run_step(controller, project_id, "separateAudio")
            continue
        if normalized == "t":
            _run_step(controller, project_id, "estimateTempo")
            continue
        if normalized.startswith("run "):
            task_type = choice[4:].strip()
            if task_type:
                _run_step(controller, project_id, task_type)


def _run_step(controller: AutoscoreController, project_id: str, task_type: str) -> None:
    try:
        result = controller.run_step(project_id, task_type)
    except Exception as exc:
        print(f"Failed: {exc}")
    else:
        print(f"{result.task_type}: {result.status}")
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
