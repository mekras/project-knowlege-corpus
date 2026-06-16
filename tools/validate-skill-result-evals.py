#!/usr/bin/env python3
"""Validate skill result scenario eval files."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_CASE_FIELDS = {
    "id": str,
    "prompt": str,
    "input_files": list,
    "expected_output": dict,
    "negative_control": dict,
    "oracle": dict,
    "application_evidence": list,
    "evaluation_surface": str,
    "assertions": list,
    "must_not": list,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate evals/result-scenarios.json files in skill directories.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Skill directories or repository roots to scan. Defaults to cwd.",
    )
    parser.add_argument(
        "--require-all",
        action="store_true",
        help=(
            "Require every discovered skill directory to have "
            "evals/result-scenarios.json."
        ),
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


def read_skill_name(skill_path: Path) -> str | None:
    in_frontmatter = False
    for line in skill_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break
        if in_frontmatter and line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
    return None


def require_non_empty_string(
    value: Any,
    field: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: field {field!r} must be a non-empty string")


def require_string_list(
    value: Any,
    field: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: field {field!r} must be a non-empty array")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(
                f"{label}: field {field!r}[{index}] must be a non-empty string",
            )


def validate_input_files(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: field 'input_files' must be a non-empty array")
        return
    for index, item in enumerate(value):
        item_label = f"{label}: input_files[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label}: must be an object")
            continue
        require_non_empty_string(item.get("path"), "path", item_label, errors)
        require_non_empty_string(item.get("purpose"), "purpose", item_label, errors)


def validate_expected_output(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label}: field 'expected_output' must be an object")
        return
    require_string_list(
        value.get("report_structure"),
        "expected_output.report_structure",
        label,
        errors,
    )


def validate_negative_control(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label}: field 'negative_control' must be an object")
        return
    require_non_empty_string(
        value.get("description"),
        "negative_control.description",
        label,
        errors,
    )
    require_non_empty_string(
        value.get("expected_failure"),
        "negative_control.expected_failure",
        label,
        errors,
    )


def validate_oracle(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label}: field 'oracle' must be an object")
        return
    require_string_list(
        value.get("success_criteria"),
        "oracle.success_criteria",
        label,
        errors,
    )
    require_string_list(
        value.get("failure_indicators"),
        "oracle.failure_indicators",
        label,
        errors,
    )


def validate_case(
    case: Any,
    index: int,
    skill_name: str,
    seen_ids: set[str],
    seen_prompts: set[str],
    errors: list[str],
) -> None:
    label = f"{skill_name}: cases[{index}]"
    if not isinstance(case, dict):
        errors.append(f"{label}: must be an object")
        return

    missing = sorted(set(REQUIRED_CASE_FIELDS) - set(case))
    if missing:
        errors.append(f"{label}: missing fields: {', '.join(missing)}")

    for field, expected_type in REQUIRED_CASE_FIELDS.items():
        if field not in case:
            continue
        if not isinstance(case[field], expected_type):
            errors.append(
                f"{label}: field {field!r} must be {expected_type.__name__}",
            )

    case_id = case.get("id")
    if isinstance(case_id, str):
        if not case_id.strip():
            errors.append(f"{label}: field 'id' must be a non-empty string")
        if case_id in seen_ids:
            errors.append(f"{label}: duplicate id {case_id!r}")
        seen_ids.add(case_id)
        if not case_id.startswith(f"{skill_name}-"):
            errors.append(
                f"{label}: id {case_id!r} must start with {skill_name!r}",
            )

    prompt = case.get("prompt")
    if isinstance(prompt, str):
        if not prompt.strip():
            errors.append(f"{label}: field 'prompt' must be a non-empty string")
        if prompt in seen_prompts:
            errors.append(f"{label}: duplicate prompt")
        seen_prompts.add(prompt)

    validate_input_files(case.get("input_files"), label, errors)
    validate_expected_output(case.get("expected_output"), label, errors)
    validate_negative_control(case.get("negative_control"), label, errors)
    validate_oracle(case.get("oracle"), label, errors)
    require_string_list(
        case.get("application_evidence"),
        "application_evidence",
        label,
        errors,
    )
    require_non_empty_string(
        case.get("evaluation_surface"),
        "evaluation_surface",
        label,
        errors,
    )
    require_string_list(case.get("assertions"), "assertions", label, errors)
    require_string_list(case.get("must_not"), "must_not", label, errors)


def validate_result_file(skill_dir: Path, require_all: bool) -> list[str]:
    errors: list[str] = []
    result_path = skill_dir / "evals" / "result-scenarios.json"
    skill_path = skill_dir / "SKILL.md"
    skill_name = read_skill_name(skill_path)

    if not skill_name:
        return [f"{skill_path}: missing frontmatter name"]

    if not result_path.exists():
        if require_all or (skill_dir / "evals").exists():
            errors.append(f"{result_path}: missing result scenario eval file")
        return errors

    data = load_json(result_path, errors)
    if data is None:
        return errors

    if not isinstance(data, dict):
        return [f"{result_path}: root must be an object"]

    if data.get("skill_name") != skill_name:
        errors.append(
            f"{result_path}: skill_name must be {skill_name!r}, "
            f"got {data.get('skill_name')!r}",
        )

    if not isinstance(data.get("source_basis"), list):
        errors.append(f"{result_path}: source_basis must be an array")

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append(f"{result_path}: cases must be a non-empty array")
        return errors

    seen_ids: set[str] = set()
    seen_prompts: set[str] = set()
    for index, case in enumerate(cases):
        validate_case(case, index, skill_name, seen_ids, seen_prompts, errors)

    return errors


def main() -> int:
    args = parse_args()
    roots = args.paths or [Path.cwd()]
    skill_dirs = find_skill_dirs(roots)
    if not skill_dirs:
        print("No skill directories found.", file=sys.stderr)
        return 1

    errors: list[str] = []
    checked = 0
    for skill_dir in skill_dirs:
        result_path = skill_dir / "evals" / "result-scenarios.json"
        errors.extend(validate_result_file(skill_dir, args.require_all))
        if result_path.exists():
            checked += 1

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"Validated {checked} result scenario eval file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
