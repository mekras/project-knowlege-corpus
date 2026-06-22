#!/usr/bin/env python3
"""Запуск модельных evals навыков через переносимый адаптер модели.

Это измерение, а не контроль качества: модельный прогон опционален и
запускается отдельной целью `apm run evals`. Детерминированный контроль качества
`apm run tests` модель не требует.

Модель вызывается через адаптер по переносимому контракту:
вызов `<адаптер> <модель>`, промпт на stdin, текст ответа на stdout. Средство
запуска само вкладывает требование вернуть JSON в текст промпта и разбирает JSON
из ответа. Привязки к конкретному CLI или модели в этом файле нет: всё задаётся
локальными настройками evals.local.yml, которые в Git не попадают.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


CONFIG_NAME = "evals.local.yml"
SAMPLE_NAME = "evals.local.yml.sample"
CLAIM_RE = re.compile(r"^### ([A-Z0-9]+-\d+)\s*$", re.MULTILINE)


TRIGGER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "should_trigger", "rationale"],
                "properties": {
                    "id": {"type": "string"},
                    "should_trigger": {"type": "boolean"},
                    "rationale": {"type": "string"},
                },
            },
        },
    },
}


ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answers"],
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "answer"],
                "properties": {
                    "id": {"type": "string"},
                    "answer": {"type": "string"},
                },
            },
        },
    },
}


JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "passed", "reasons", "missing"],
                "properties": {
                    "id": {"type": "string"},
                    "passed": {"type": "boolean"},
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "missing": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


# Тип вызова модели: (prompt, schema) -> разобранный JSON-объект.
ModelCall = Callable[[str, dict[str, Any]], dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Запустить модельные evals навыков через адаптер модели.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Каталоги навыков или корни репозитория для обхода. По умолчанию текущий каталог.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("APM_EVAL_CONFIG", CONFIG_NAME)),
        help="Путь к локальным настройкам evals. По умолчанию APM_EVAL_CONFIG или evals.local.yml.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("APM_EVAL_LIMIT", "0")),
        help="Ограничить число result-сценариев. 0 означает все сценарии.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help=(
            "Запустить только проверку с указанным id. Можно повторять. "
            "Также читается из APM_EVAL_CASE_ID или APM_EVAL_CASE_IDS "
            "через запятую."
        ),
    )
    args = parser.parse_args()
    env_case_ids = []
    for name in ("APM_EVAL_CASE_ID", "APM_EVAL_CASE_IDS"):
        raw_value = os.environ.get(name, "")
        env_case_ids.extend(
            part.strip()
            for part in raw_value.split(",")
            if part.strip()
        )
    args.case_id = [*env_case_ids, *args.case_id]
    return args


def bootstrap_config(repo_root: Path, config_path: Path) -> None:
    """Создать локальные настройки из образца и скрыть их от Git."""
    sample = repo_root / SAMPLE_NAME
    if not sample.exists():
        print(
            f"Нет ни {config_path.name}, ни образца {SAMPLE_NAME}. "
            "Модельные evals настроить нельзя.",
            file=sys.stderr,
        )
        return
    config_path.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    exclude = repo_root / ".git" / "info" / "exclude"
    rel = config_path.name
    if exclude.parent.is_dir():
        lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
        if rel not in {line.strip() for line in lines}:
            with exclude.open("a", encoding="utf-8") as handle:
                handle.write(f"{rel}\n")
    print(
        f"Созданы локальные настройки {rel} из образца и добавлены в "
        ".git/info/exclude.\n"
        f"Заполните в нём adapters и models, затем повторите `apm run evals`.\n"
        "Модельные evals пока пропущены.",
        flush=True,
    )


def load_config(repo_root: Path, config_path: Path) -> dict[str, Any] | None:
    """Прочитать настройки evals. Вернуть None, если запуск нужно пропустить."""
    if not config_path.is_absolute():
        config_path = repo_root / config_path
    if not config_path.exists():
        bootstrap_config(repo_root, config_path)
        return None
    try:
        import yaml
    except ImportError:
        print(
            "Для модельных evals нужен PyYAML (pip install pyyaml). "
            "Модельные evals пропущены.",
            file=sys.stderr,
        )
        return None
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        print(f"Настройки {config_path} должны быть YAML-объектом.", file=sys.stderr)
        return None

    raw_adapters = data.get("adapters")
    if not isinstance(raw_adapters, dict) or not raw_adapters:
        print(
            f"В настройках {config_path.name} не задан раздел adapters "
            "(имя адаптера -> команда). Модельные evals пропущены.",
            file=sys.stderr,
        )
        return None
    adapters = {name: shlex.split(str(command)) for name, command in raw_adapters.items()}

    env_model = os.environ.get("APM_EVAL_MODEL")
    model_specs = [env_model] if env_model else list(data.get("models") or [])
    judge_spec = os.environ.get("APM_EVAL_JUDGE_MODEL") or data.get("judge")
    timeout = int(os.environ.get("APM_EVAL_TIMEOUT") or data.get("timeout") or 900)

    if not model_specs:
        print(
            f"В настройках {config_path.name} не заданы models. "
            "Модельные evals пропущены.",
            file=sys.stderr,
        )
        return None

    spec_errors: list[str] = []
    runs = [
        resolve_run(spec, adapters, f"models[{index}]", spec_errors)
        for index, spec in enumerate(model_specs)
    ]
    runs = [run for run in runs if run]
    if judge_spec:
        judge = resolve_run(judge_spec, adapters, "judge", spec_errors)
    else:
        judge = None
        spec_errors.append(
            "judge: не задана модель-судья; укажите judge в формате адаптер:модель. "
            "Судья не берётся из models по умолчанию: в models держите слабые модели "
            "для прогона, а судьёй назначайте сильную модель."
        )

    if spec_errors or not runs or judge is None:
        for error in spec_errors:
            print(error, file=sys.stderr)
        print(
            f"Модельные evals пропущены из-за ошибок в {config_path.name}.",
            file=sys.stderr,
        )
        return None
    return {"runs": runs, "judge": judge, "timeout": timeout}


def resolve_run(
    spec: Any,
    adapters: dict[str, list[str]],
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    """Разобрать запись `адаптер:модель` и связать её с командой адаптера."""
    if not isinstance(spec, str) or ":" not in spec:
        errors.append(f"{label}: ожидается формат адаптер:модель, получено {spec!r}")
        return None
    name, model = spec.split(":", 1)
    name, model = name.strip(), model.strip()
    if name not in adapters:
        errors.append(
            f"{label}: неизвестный адаптер {name!r}; задайте его в разделе adapters",
        )
        return None
    if not model:
        errors.append(f"{label}: не указана модель в {spec!r}")
        return None
    return {"adapter": adapters[name], "model": model, "label": spec}


def extract_json(text: str) -> dict[str, Any]:
    """Достать JSON-объект из текстового ответа модели (best-effort)."""
    text = text.strip()
    candidates: list[str] = []
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    first = first_json_object(text)
    if first:
        candidates.append(first)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise RuntimeError(f"Модель не вернула разбираемый JSON:\n{text}")


def first_json_object(text: str) -> str:
    """Вернуть первый сбалансированный JSON-объект в тексте."""
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def make_model_call(adapter: list[str], model: str, timeout: int) -> ModelCall:
    """Собрать вызов модели через адаптер по контракту prompt -> текст."""

    def call(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        full_prompt = (
            f"{prompt}\n\n"
            "Верни только один JSON-объект без пояснений и без оформления в "
            "кодовый блок, строго соответствующий схеме:\n"
            f"{json.dumps(schema, ensure_ascii=False)}\n"
        )
        try:
            completed = subprocess.run(
                [*adapter, model],
                input=full_prompt,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Адаптер модели не найден: {' '.join(adapter)}. "
                "Проверьте adapter в настройках evals.",
            ) from exc
        if completed.returncode != 0:
            raise RuntimeError(
                f"Адаптер вернул код {completed.returncode}.\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            )
        return extract_json(completed.stdout)

    return call


def find_skill_dirs(paths: list[Path]) -> list[Path]:
    skill_dirs: set[Path] = set()
    for path in paths:
        path = path.resolve()
        if (path / "SKILL.md").is_file():
            skill_dirs.add(path)
            continue
        for skill_file in path.rglob("SKILL.md"):
            if ".git" in skill_file.parts:
                continue
            skill_dirs.add(skill_file.parent)
    return sorted(skill_dirs)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_frontmatter(skill_path: Path) -> dict[str, str]:
    frontmatter: dict[str, str] = {}
    in_frontmatter = False
    current_key: str | None = None
    current_lines: list[str] = []

    for line in skill_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break
        if not in_frontmatter:
            continue
        if line and not line.startswith((" ", "\t")) and ":" in line:
            if current_key:
                frontmatter[current_key] = " ".join(current_lines).strip()
            current_key, value = line.split(":", 1)
            current_key = current_key.strip()
            current_lines = [value.strip().strip(">")]
            continue
        if current_key:
            current_lines.append(line.strip())

    if current_key:
        frontmatter[current_key] = " ".join(current_lines).strip()
    return frontmatter


def collect_trigger_cases(skill_dirs: list[Path]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for skill_dir in skill_dirs:
        trigger_path = skill_dir / "evals" / "triggers.json"
        if not trigger_path.exists():
            continue
        skill_path = skill_dir / "SKILL.md"
        frontmatter = read_frontmatter(skill_path)
        trigger_data = load_json(trigger_path)
        skill_name = trigger_data["skill_name"]
        for case in trigger_data["cases"]:
            cases.append(
                {
                    "id": case["id"],
                    "skill_name": skill_name,
                    "skill_description": frontmatter.get("description", ""),
                    "prompt": case["prompt"],
                    "expected_should_trigger": case["should_trigger"],
                    "expected_rationale": case["rationale"],
                },
            )
    return cases


def filter_trigger_cases(
    cases: list[dict[str, Any]],
    case_ids: set[str],
) -> list[dict[str, Any]]:
    if not case_ids:
        return cases
    return [case for case in cases if case["id"] in case_ids]


def trigger_prompt(cases: list[dict[str, Any]]) -> str:
    payload = [
        {
            "id": case["id"],
            "skill_name": case["skill_name"],
            "skill_description": case["skill_description"],
            "user_prompt": case["prompt"],
        }
        for case in cases
    ]
    return (
        "Ты проверяешь маршрутизацию навыков агента.\n"
        "Для каждого кейса реши, должен ли указанный навык сработать для "
        "пользовательского запроса. Опирайся на description навыка как на "
        "контракт маршрутизации. Не угадывай по названию навыка, если "
        "description не покрывает ситуацию.\n"
        f"Кейсы:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    )


def run_trigger_evals(
    *,
    cases: list[dict[str, Any]],
    call: ModelCall,
) -> list[str]:
    if not cases:
        print("Модельные trigger-evals не найдены.", flush=True)
        return []

    print(f"Запускаю модельные trigger-evals: {len(cases)} кейс(ов).", flush=True)
    errors: list[str] = []
    missing_cases: list[dict[str, Any]] = []
    sorted_cases = sorted(cases, key=lambda item: item["skill_name"])
    for skill_name, grouped_cases in itertools.groupby(
        sorted_cases,
        key=lambda item: item["skill_name"],
    ):
        skill_cases = list(grouped_cases)
        print(
            f"Проверяю trigger-сценарии навыка {skill_name}: {len(skill_cases)}.",
            flush=True,
        )
        result = call(trigger_prompt(skill_cases), TRIGGER_SCHEMA)
        actual_by_id = {item.get("id"): item for item in result.get("results", [])}
        for case in skill_cases:
            actual = actual_by_id.get(case["id"])
            if not actual:
                missing_cases.append(case)
                continue
            if actual.get("should_trigger") != case["expected_should_trigger"]:
                errors.append(
                    f"{case['id']}: ожидалось should_trigger="
                    f"{case['expected_should_trigger']}, модель вернула "
                    f"{actual.get('should_trigger')}. Обоснование: "
                    f"{actual.get('rationale', '')}",
                )
    for case in missing_cases:
        print(f"Повторяю trigger-сценарий {case['id']} отдельно.", flush=True)
        result = call(trigger_prompt([case]), TRIGGER_SCHEMA)
        actual_by_id = {item.get("id"): item for item in result.get("results", [])}
        actual = actual_by_id.get(case["id"])
        if not actual:
            errors.append(f"{case['id']}: модель не вернула результат.")
            continue
        if actual.get("should_trigger") != case["expected_should_trigger"]:
            errors.append(
                f"{case['id']}: ожидалось should_trigger="
                f"{case['expected_should_trigger']}, модель вернула "
                f"{actual.get('should_trigger')}. Обоснование: "
                f"{actual.get('rationale', '')}",
            )
    if not errors:
        print(f"Пройдено модельных trigger-evals: {len(cases)} из {len(cases)}.", flush=True)
    return errors


def collect_result_groups(
    skill_dirs: list[Path],
    limit: int,
) -> list[tuple[Path, dict[str, Any], list[dict[str, Any]]]]:
    remaining = limit
    groups: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]] = []
    for skill_dir in skill_dirs:
        result_path = skill_dir / "evals" / "result-scenarios.json"
        if not result_path.exists():
            continue
        data = load_json(result_path)
        cases = data["cases"]
        if limit > 0:
            if remaining <= 0:
                break
            cases = cases[:remaining]
            remaining -= len(cases)
        groups.append((skill_dir, data, cases))
    return groups


def filter_result_groups(
    groups: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]],
    case_ids: set[str],
) -> list[tuple[Path, dict[str, Any], list[dict[str, Any]]]]:
    if not case_ids:
        return groups
    filtered: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]] = []
    for skill_dir, data, cases in groups:
        selected = [case for case in cases if case["id"] in case_ids]
        if selected:
            filtered.append((skill_dir, data, selected))
    return filtered


def extract_claim_block(statement_text: str, claim_id: str) -> str:
    matches = list(CLAIM_RE.finditer(statement_text))
    for index, match in enumerate(matches):
        if match.group(1) != claim_id:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(statement_text)
        return statement_text[start:end].strip()
    return ""


def collect_source_basis_text(repo_root: Path, data: dict[str, Any]) -> list[dict[str, str]]:
    basis_text: list[dict[str, str]] = []
    for item in data.get("source_basis", []):
        claim_id = item.get("claim_id")
        statement_path = item.get("statement_path")
        if not isinstance(claim_id, str) or not isinstance(statement_path, str):
            continue
        path = repo_root / statement_path
        if not path.is_file():
            continue
        statement_text = path.read_text(encoding="utf-8")
        basis_text.append(
            {
                "claim_id": claim_id,
                "statement_path": statement_path,
                "text": extract_claim_block(statement_text, claim_id),
            },
        )
    return basis_text


def answer_prompt(
    repo_root: Path,
    skill_dir: Path,
    data: dict[str, Any],
    cases: list[dict[str, Any]],
) -> str:
    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    target_cases = [
        {
            "id": case["id"],
            "prompt": case["prompt"],
            "input_files": case.get("input_files", []),
            "required_corpus_claims": case.get("required_corpus_claims", []),
            "expected_output": case.get("expected_output", {}),
            "assertions": case.get("assertions", []),
            "must_not": case.get("must_not", []),
        }
        for case in cases
    ]
    return (
        "Ты проверяемая модель. Примени навык к каждому пользовательскому "
        "сценарию и дай ответ так, как если бы пользователь реально попросил "
        "выполнить эту задачу. Ответ должен быть пригоден для проверки: покажи "
        "применённую процедуру навыка, конкретные выводы/findings, важные "
        "ограничения, действия или изменяемые файлы. Если даны "
        "required_corpus_claims, используй именно эти claim_id для ключевых "
        "выводов и не подменяй их похожими claim_id из source_basis. "
        "Используй expected_output, assertions и must_not как контракт "
        "приёмки результата: ответ должен содержать ожидаемую структуру, "
        "findings и проверяемые сведения, но не пересказывать контракт отдельно "
        "и не ссылаться на него как на тестовые данные. "
        "Поле input_files в сценарии описывает доступный fixture задачи. "
        "Если у элемента есть content, считай это содержимым файла. Если "
        "content отсутствует, используй prompt и purpose как единственные "
        "доступные факты о файле; не заявляй, что файл отсутствует в рабочей "
        "области, и не ищи его в текущем cwd. "
        "Если сценарий требует изменить файлы, а содержимое файлов не дано, "
        "верни проверяемый результат изменения: имена создаваемых или "
        "изменяемых файлов, какие фрагменты куда переносятся или удаляются, "
        "и какие правила остаются в каждом файле. Не отвечай планом: формулируй "
        "результат так, как будто применение навыка уже выполнено. Для каждого "
        "ключевого вывода используй поля severity, corpus_claims, "
        "observed_problem, expected_conclusion и acceptable_fix_direction. "
        "Не упоминай, что это тест, "
        "и не оценивай сам себя.\n"
        f"Навык:\n{skill_text}\n\n"
        f"Сценарии:\n{json.dumps(target_cases, ensure_ascii=False, indent=2)}\n"
        "Фактические основания source_basis:\n"
        f"{json.dumps(collect_source_basis_text(repo_root, data), ensure_ascii=False, indent=2)}\n"
    )


def judge_prompt(
    data: dict[str, Any],
    cases: list[dict[str, Any]],
    answers: list[dict[str, str]],
) -> str:
    expected_cases = {case["id"]: case for case in data["cases"] if case in cases}
    payload = {
        "skill_name": data["skill_name"],
        "cases": [expected_cases[case["id"]] for case in cases],
        "answers": answers,
    }
    return (
        "Ты строгий судья evals навыков агента.\n"
        "Для каждого ответа проверь, реально ли модель применила навык к "
        "сценарию. Ответ проходит только если он удовлетворяет expected_output, "
        "application_evidence, oracle.success_criteria и assertions, а также не "
        "нарушает must_not и не содержит oracle.failure_indicators. Не засчитывай "
        "общие советы, пересказ схемы или формальное совпадение заголовков без "
        "признаков применения навыка. Оценивай только текст ответа, потому что "
        "runner не создаёт fixture-репозиторий для фактических файловых правок. "
        "Если assertion говорит, что результат меняет или создаёт файлы, считай "
        "его выполненным только когда ответ содержит конкретные имена файлов и "
        "проверяемые сведения о переносимых, удаляемых или добавляемых правилах.\n"
        f"Данные для проверки:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    )


def run_result_evals(
    *,
    repo_root: Path,
    groups: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]],
    call: ModelCall,
    judge_call: ModelCall,
) -> list[str]:
    total = sum(len(cases) for _, _, cases in groups)
    if not total:
        print("Модельные result-evals не найдены.", flush=True)
        return []

    print(f"Запускаю модельные result-evals: {total} сценариев.", flush=True)
    errors: list[str] = []
    passed = 0
    for skill_dir, data, cases in groups:
        print(
            f"Проверяю result-сценарии навыка {data['skill_name']}: {len(cases)}.",
            flush=True,
        )
        for case in cases:
            single_case = [case]
            answer_result = call(
                answer_prompt(repo_root, skill_dir, data, single_case),
                ANSWER_SCHEMA,
            )
            answers = answer_result.get("answers", [])
            judge_result = judge_call(
                judge_prompt(data, single_case, answers),
                JUDGE_SCHEMA,
            )
            verdicts = {
                item.get("id"): item for item in judge_result.get("results", [])
            }
            verdict = verdicts.get(case["id"])
            if not verdict:
                errors.append(f"{case['id']}: судья не вернул результат.")
                continue
            if verdict.get("passed") is True:
                passed += 1
                continue
            reasons = "; ".join(verdict.get("reasons", []))
            missing = "; ".join(verdict.get("missing", []))
            errors.append(
                f"{case['id']}: сценарий не пройден. Причины: {reasons}. "
                f"Не хватает: {missing}.",
            )
        print(
            f"Завершена проверка навыка {data['skill_name']}.",
            flush=True,
        )
    if not errors:
        print(f"Пройдено модельных result-evals: {passed} из {total}.", flush=True)
    return errors


def run_for_target(
    *,
    repo_root: Path,
    run: dict[str, Any],
    judge: dict[str, Any],
    timeout: int,
    trigger_cases: list[dict[str, Any]],
    result_groups: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]],
) -> list[str]:
    print(f"\n=== Применение навыков: {run['label']} ===", flush=True)
    print(f"Оценка результатов: {judge['label']}.", flush=True)
    call = make_model_call(run["adapter"], run["model"], timeout)
    judge_call = make_model_call(judge["adapter"], judge["model"], timeout)
    trigger_errors = run_trigger_evals(cases=trigger_cases, call=call)
    result_errors = run_result_evals(
        repo_root=repo_root,
        groups=result_groups,
        call=call,
        judge_call=judge_call,
    )
    return [f"[{run['label']}] {error}" for error in trigger_errors + result_errors]


def main() -> int:
    args = parse_args()
    roots = args.paths or [Path.cwd()]
    repo_root = Path.cwd().resolve()
    case_ids = set(args.case_id)

    config = load_config(repo_root, args.config)
    if config is None:
        # Bootstrap или нехватка настроек уже сообщены. Это не дефект контроля
        # качества: модельные evals опциональны, поэтому выходим без ошибки.
        return 0

    skill_dirs = find_skill_dirs(roots)
    if not skill_dirs:
        print("Каталоги навыков не найдены.", file=sys.stderr)
        return 1

    all_trigger_cases = collect_trigger_cases(skill_dirs)
    all_result_groups = collect_result_groups(skill_dirs, 0)
    if case_ids:
        known_case_ids = {case["id"] for case in all_trigger_cases}
        known_case_ids.update(
            case["id"]
            for _, _, cases in all_result_groups
            for case in cases
        )
        missing = sorted(case_ids - known_case_ids)
        if missing:
            print(
                "Проверки с указанными id не найдены: " + ", ".join(missing),
                file=sys.stderr,
            )
            return 1

    trigger_cases = filter_trigger_cases(all_trigger_cases, case_ids)
    result_groups = filter_result_groups(
        all_result_groups if case_ids else collect_result_groups(skill_dirs, args.limit),
        case_ids,
    )

    errors: list[str] = []
    for run in config["runs"]:
        errors.extend(
            run_for_target(
                repo_root=repo_root,
                run=run,
                judge=config["judge"],
                timeout=config["timeout"],
                trigger_cases=trigger_cases,
                result_groups=result_groups,
            )
        )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"Модельные evals не пройдены: {len(errors)} ошибка(ок).", file=sys.stderr)
        return 1

    print("\nМодельные evals пройдены.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
