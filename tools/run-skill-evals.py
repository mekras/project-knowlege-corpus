#!/usr/bin/env python3
"""Run lightweight checks for skill result-scenario cases."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check result-scenario cases for selected skill directories.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Skill directories or repository roots to scan. Defaults to cwd.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only the scenario case with this id. May be repeated.",
    )
    return parser.parse_args()


def is_git_ignored(path: Path) -> bool:
    try:
        git_path = str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        git_path = str(path)
    result = subprocess.run(
        ["git", "check-ignore", "-q", git_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def find_skill_dirs(paths: list[Path]) -> list[Path]:
    skill_dirs: set[Path] = set()
    for path in paths:
        path = path.resolve()
        if is_git_ignored(path):
            continue
        if (path / "SKILL.md").is_file():
            skill_dirs.add(path)
            continue
        for skill_file in path.rglob("SKILL.md"):
            if ".git" in skill_file.parts or is_git_ignored(skill_file.parent):
                continue
            skill_dirs.add(skill_file.parent)
    return sorted(skill_dirs)


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
    return None


def selected_case_ids(args: argparse.Namespace) -> set[str]:
    case_ids = set(args.case_id)
    env_single = os.environ.get("APM_EVAL_CASE_ID")
    env_many = os.environ.get("APM_EVAL_CASE_IDS")
    if env_single:
        case_ids.add(env_single)
    if env_many:
        case_ids.update(
            case_id.strip()
            for case_id in env_many.replace(",", " ").split()
            if case_id.strip()
        )
    return case_ids


def existing_path(path_value: Any, scenario_path: Path, errors: list[str]) -> None:
    if not isinstance(path_value, str) or not path_value.strip():
        return
    if not path_value.startswith(".apm/"):
        return
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.exists():
        return
    errors.append(f"{scenario_path}: input file does not exist: {path_value}")


def collect_cases(skill_dirs: list[Path], errors: list[str]) -> dict[str, tuple[Path, dict[str, Any]]]:
    cases: dict[str, tuple[Path, dict[str, Any]]] = {}
    for skill_dir in skill_dirs:
        scenario_path = skill_dir / "evals" / "result-scenarios.json"
        if not scenario_path.exists():
            continue
        data = load_json(scenario_path, errors)
        if not isinstance(data, dict):
            continue
        scenario_cases = data.get("cases")
        if not isinstance(scenario_cases, list):
            continue
        for index, case in enumerate(scenario_cases):
            if not isinstance(case, dict):
                continue
            case_id = case.get("id")
            if not isinstance(case_id, str) or not case_id.strip():
                continue
            if case_id in cases:
                errors.append(f"{scenario_path}: duplicate case id: {case_id}")
                continue
            cases[case_id] = (scenario_path, case)
            for item in case.get("input_files", []):
                if isinstance(item, dict):
                    existing_path(item.get("path"), scenario_path, errors)
                else:
                    errors.append(
                        f"{scenario_path}: {case_id}: input_files[{index}] must be an object",
                    )
    return cases


def main() -> int:
    args = parse_args()
    roots = args.paths or [Path.cwd()]
    skill_dirs = find_skill_dirs(roots)
    if not skill_dirs:
        print("No skill directories found.", file=sys.stderr)
        return 1

    errors: list[str] = []
    cases = collect_cases(skill_dirs, errors)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    if not cases:
        print("No result scenario cases found.", file=sys.stderr)
        return 1

    requested = selected_case_ids(args)
    if requested:
        unknown = sorted(requested - set(cases))
        if unknown:
            print(
                "Unknown result scenario case id(s): " + ", ".join(unknown),
                file=sys.stderr,
            )
            return 1
        cases = {case_id: cases[case_id] for case_id in sorted(requested)}

    print(f"Checked {len(cases)} result scenario case(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
