#!/usr/bin/env python3
"""Validate a project knowledge corpus layout.

This script validates the optional portable layout described in
source-inventory/references/corpus-layout-contract.md. It is intentionally
generic: project-specific adapters and semantic checks should remain in the
project that owns the corpus.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - depends on target project environment.
    yaml = None


SOURCE_REQUIRED = {
    "id",
    "slug",
    "title",
    "access",
    "status",
    "platform",
    "kind",
    "adapter",
    "reliability",
    "refresh_policy",
}

ITEM_REQUIRED = {
    "id",
    "title",
    "access",
    "status",
    "workflow_stage",
}

STATEMENT_REQUIRED = {
    "id",
    "source_id",
    "item_id",
    "status",
    "text",
    "excerpt",
    "artifact",
    "checked_at",
    "scope",
    "open_questions",
}

DEFAULT_ALLOWED_STAGES = {
    "indexed",
    "needs_fetch",
    "fetched",
    "needs_transcript",
    "raw_transcribed",
    "normalized",
    "statements_extracted",
    "source_checked",
    "blocked",
    "rejected",
}

STATEMENT_TEXT_FORBIDDEN_PREFIXES = (
    "в посте сказано",
    "в посте говорится",
    "в посте заявлено",
    "в посте указано",
    "в посте описано",
    "в посте сообщается",
    "автор считает",
    "автор сообщает",
    "автор утверждает",
    "автор пишет",
    "автор указывает",
    "автор заявляет",
    "по оценке автора",
    "по сообщению автора",
    "по словам автора",
    "по тексту поста",
    "по тексту источника",
    "по источнику",
)

REDACTION_PLACEHOLDER_PATTERNS = (
    "[обезличено]",
    "[номер горячей линии]",
    "[номер телефона]",
    "[номер email]",
    "[номер e-mail]",
    "[редактировано:",
)


def load_yaml(path: Path) -> Any:
    if yaml is None:
        raise RuntimeError("PyYAML is required: pip install PyYAML")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def walk_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for child in value.values():
            result.extend(walk_values(child))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for child in value:
            result.extend(walk_values(child))
        return result
    return []


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_bad_absolute_path(value: str) -> bool:
    return value.startswith("/") and "://" not in value


def contains_redaction_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(pattern in lowered for pattern in REDACTION_PLACEHOLDER_PATTERNS)


class Validator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.contract_path = self.root / "corpus.yml"
        self.catalog_path = self.root / "catalog.yml"
        self.errors: list[str] = []
        self.allowed_stages = set(DEFAULT_ALLOWED_STAGES)
        self.source_ids: set[str] = set()
        self.item_ids: set[str] = set()

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def add_value_errors(self, path_label: str, value: Any) -> None:
        for item in walk_values(value):
            if is_bad_absolute_path(item):
                self.errors.append(f"{path_label}: absolute local path is not allowed: {item}")

    def validate(self) -> int:
        try:
            self.validate_contract()
            source_dirs = self.source_dirs()
            for source_dir in source_dirs:
                self.validate_source(source_dir)
            self.validate_catalog(source_dirs)
            self.validate_global_items_index(source_dirs)
        except RuntimeError as exc:
            self.errors.append(str(exc))

        if self.errors:
            print("Corpus validation failed:")
            for error in self.errors:
                print(f"- {error}")
            return 1

        print(f"Corpus validation passed: {len(self.source_ids)} source(s) checked.")
        return 0

    def validate_contract(self) -> None:
        if not self.contract_path.exists():
            self.errors.append("missing corpus.yml")
            return

        contract = load_yaml(self.contract_path)
        if not isinstance(contract, dict):
            self.errors.append("corpus.yml must be a mapping")
            return

        for key in ("contract_version", "tracked_data", "local_data", "source_units"):
            if key not in contract:
                self.errors.append(f"corpus.yml missing required key: {key}")

        stages = contract.get("workflow_stages")
        if isinstance(stages, list) and all(isinstance(item, str) for item in stages):
            self.allowed_stages = set(stages)

        self.add_value_errors("corpus.yml", contract)

    def source_dirs(self) -> list[Path]:
        data_root = self.root / "data"
        if not data_root.exists():
            return []
        return sorted(path.parent for path in data_root.glob("*/source.yml"))

    def validate_catalog(self, source_dirs: list[Path]) -> None:
        if not self.catalog_path.exists():
            self.errors.append("missing catalog.yml")
            return

        catalog = load_yaml(self.catalog_path)
        if not isinstance(catalog, dict) or not isinstance(catalog.get("sources"), list):
            self.errors.append("catalog.yml must contain a sources list")
            return

        seen: set[str] = set()
        for index, source in enumerate(catalog["sources"], start=1):
            prefix = f"catalog.yml: source #{index}"
            if not isinstance(source, dict):
                self.errors.append(f"{prefix}: source must be a mapping")
                continue
            source_id = source.get("id")
            path = source.get("path")
            if isinstance(source_id, str):
                seen.add(source_id)
            else:
                self.errors.append(f"{prefix}: id must be a string")
            if not isinstance(path, str) or not (self.root / path / "source.yml").exists():
                self.errors.append(f"{prefix}: source path is invalid: {path}")

        expected_ids = set()
        for source_dir in source_dirs:
            source = load_yaml(source_dir / "source.yml")
            source_id = source.get("id") if isinstance(source, dict) else None
            if isinstance(source_id, str):
                expected_ids.add(source_id)

        missing = expected_ids - seen
        extra = seen - expected_ids
        if missing:
            self.errors.append(f"catalog.yml missing sources: {', '.join(sorted(missing))}")
        if extra:
            self.errors.append(f"catalog.yml references unknown sources: {', '.join(sorted(extra))}")

    def validate_global_items_index(self, source_dirs: list[Path]) -> None:
        path = self.root / "index" / "items.yml"
        if not path.exists():
            return

        rel = self.rel(path)
        data = load_yaml(path)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            self.errors.append(f"{rel}: items must be a list")
            return

        global_by_id: dict[str, Any] = {}
        for index, item in enumerate(items, start=1):
            prefix = f"{rel}: item #{index}"
            if not isinstance(item, dict):
                self.errors.append(f"{prefix}: item must be a mapping")
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str):
                self.errors.append(f"{prefix}: id must be a string")
                continue
            if item_id in global_by_id:
                self.errors.append(f"{prefix}: duplicate item id: {item_id}")
            global_by_id[item_id] = item

        expected_ids: set[str] = set()
        for source_dir in source_dirs:
            source = load_yaml(source_dir / "source.yml")
            source_id = source.get("id") if isinstance(source, dict) else None
            source_items_path = source_dir / "items.yml"
            if not source_items_path.exists():
                continue
            source_items = load_yaml(source_items_path)
            source_list = source_items.get("items") if isinstance(source_items, dict) else None
            if not isinstance(source_id, str) or not isinstance(source_list, list):
                continue
            for source_item in source_list:
                if not isinstance(source_item, dict):
                    continue
                item_id = source_item.get("id")
                if not isinstance(item_id, str):
                    continue
                expected_ids.add(item_id)
                global_item = global_by_id.get(item_id)
                if global_item is None:
                    self.errors.append(f"{rel}: missing source item: {item_id}")
                    continue

                item_path = source_item.get("path")
                expected_path = None
                if isinstance(item_path, str):
                    expected_path = (source_dir / item_path).relative_to(self.root).as_posix()
                expected_fields = {
                    "source_id": source_id,
                    "path": expected_path,
                    "title": source_item.get("title"),
                    "workflow_stage": source_item.get("workflow_stage"),
                    "access": source_item.get("access"),
                }
                for field, expected in expected_fields.items():
                    if global_item.get(field) != expected:
                        self.errors.append(f"{rel}: {item_id} field {field} is out of sync")

        extra_ids = sorted(set(global_by_id) - expected_ids)
        if extra_ids:
            self.errors.append(f"{rel}: references unknown items: {', '.join(extra_ids)}")

    def validate_source(self, source_dir: Path) -> None:
        path = source_dir / "source.yml"
        rel = self.rel(path)
        source = load_yaml(path)
        if not isinstance(source, dict):
            self.errors.append(f"{rel}: source card must be a mapping")
            return

        missing = sorted(SOURCE_REQUIRED - source.keys())
        if missing:
            self.errors.append(f"{rel}: missing source fields: {', '.join(missing)}")

        source_id = source.get("id")
        if isinstance(source_id, str):
            if source_id in self.source_ids:
                self.errors.append(f"{rel}: duplicate source id: {source_id}")
            self.source_ids.add(source_id)
        else:
            self.errors.append(f"{rel}: id must be a string")

        access = source.get("access")
        if not isinstance(access, dict):
            self.errors.append(f"{rel}: access must be a mapping")
        elif not nonempty_string(access.get("default")):
            self.errors.append(f"{rel}: access.default must be non-empty text")

        self.add_value_errors(rel, source)
        self.validate_items(source_dir, source_id)
        self.validate_unit_dirs(source_dir, source_id)

    def validate_items(self, source_dir: Path, source_id: Any) -> None:
        path = source_dir / "items.yml"
        rel = self.rel(path)
        if not path.exists():
            self.errors.append(f"{rel}: missing items.yml")
            return

        data = load_yaml(path)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            self.errors.append(f"{rel}: items must be a list")
            return

        for index, item in enumerate(items, start=1):
            self.validate_item(source_dir, item, source_id, f"{rel}: item #{index}")

    def validate_item(self, source_dir: Path, item: Any, source_id: Any, prefix: str) -> None:
        if not isinstance(item, dict):
            self.errors.append(f"{prefix}: item must be a mapping")
            return

        missing = sorted(ITEM_REQUIRED - item.keys())
        if missing:
            self.errors.append(f"{prefix}: missing fields: {', '.join(missing)}")

        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in self.item_ids:
                self.errors.append(f"{prefix}: duplicate item id: {item_id}")
            self.item_ids.add(item_id)
        else:
            self.errors.append(f"{prefix}: id must be a string")

        if source_id and item.get("source_id") not in (None, source_id):
            self.errors.append(f"{prefix}: source_id does not match {source_id}")
        if not nonempty_string(item.get("access")):
            self.errors.append(f"{prefix}: access must be non-empty text")

        stage = item.get("workflow_stage")
        if stage and stage not in self.allowed_stages:
            self.errors.append(f"{prefix}: unknown workflow_stage: {stage}")

        item_path = item.get("path")
        if isinstance(item_path, str) and not (source_dir / item_path).exists():
            self.errors.append(f"{prefix}: item path does not exist: {item_path}")

        self.add_value_errors(prefix, item)

    def validate_unit_dirs(self, source_dir: Path, source_id: Any) -> None:
        for units_dir in sorted(path for path in source_dir.iterdir() if path.is_dir()):
            for unit_dir in sorted(path for path in units_dir.iterdir() if path.is_dir()):
                item_path = unit_dir / "item.yml"
                if item_path.exists():
                    item = load_yaml(item_path)
                    self.validate_unit_item(item, source_id, item_path)
                self.validate_unit_artifacts(unit_dir)
                statements_path = unit_dir / "statements.yml"
                if statements_path.exists():
                    item_id = item.get("id") if item_path.exists() and isinstance(item, dict) else None
                    self.validate_statements(statements_path, source_id, item_id)

    def validate_unit_item(self, item: Any, source_id: Any, path: Path) -> None:
        rel = self.rel(path)
        if not isinstance(item, dict):
            self.errors.append(f"{rel}: item must be a mapping")
            return

        missing = sorted(ITEM_REQUIRED - item.keys())
        if missing:
            self.errors.append(f"{rel}: missing fields: {', '.join(missing)}")

        item_id = item.get("id")
        if isinstance(item_id, str) and item_id not in self.item_ids:
            self.errors.append(f"{rel}: item is not present in source items.yml: {item_id}")

        if source_id and item.get("source_id") not in (None, source_id):
            self.errors.append(f"{rel}: source_id does not match {source_id}")
        if not nonempty_string(item.get("access")):
            self.errors.append(f"{rel}: access must be non-empty text")

        stage = item.get("workflow_stage")
        if stage and stage not in self.allowed_stages:
            self.errors.append(f"{rel}: unknown workflow_stage: {stage}")

        self.add_value_errors(rel, item)

        files = item.get("files", {})
        if files and not isinstance(files, dict):
            self.errors.append(f"{rel}: files must be a mapping")
            return

        for artifact in files.get("tracked", []):
            if not (path.parent / artifact).exists():
                self.errors.append(f"{rel}: tracked file does not exist: {artifact}")
        for artifact in files.get("local", []):
            if ".tmp." not in artifact:
                self.errors.append(f"{rel}: local file must use *.tmp.* name: {artifact}")

    def validate_unit_artifacts(self, unit_dir: Path) -> None:
        for artifact_path in sorted(unit_dir.iterdir()):
            if not artifact_path.is_file() or artifact_path.suffix not in {".md", ".txt"}:
                continue
            text = artifact_path.read_text(encoding="utf-8")
            if contains_redaction_placeholder(text):
                rel = self.rel(artifact_path)
                self.errors.append(
                    f"{rel}: inline redaction placeholder found; describe restrictions in metadata"
                )

    def validate_statements(self, path: Path, source_id: Any, item_id: Any) -> None:
        rel = self.rel(path)
        data = load_yaml(path)
        statements = data.get("statements") if isinstance(data, dict) else None
        if not isinstance(statements, list):
            self.errors.append(f"{rel}: statements must be a list")
            return

        seen: set[str] = set()
        for index, statement in enumerate(statements, start=1):
            prefix = f"{rel}: statement #{index}"
            if not isinstance(statement, dict):
                self.errors.append(f"{prefix}: statement must be a mapping")
                continue

            missing = sorted(STATEMENT_REQUIRED - statement.keys())
            if missing:
                self.errors.append(f"{prefix}: missing fields: {', '.join(missing)}")

            statement_id = statement.get("id")
            if isinstance(statement_id, str):
                if statement_id in seen:
                    self.errors.append(f"{prefix}: duplicate statement id: {statement_id}")
                seen.add(statement_id)
            else:
                self.errors.append(f"{prefix}: id must be a string")

            if source_id and statement.get("source_id") != source_id:
                self.errors.append(f"{prefix}: source_id does not match {source_id}")
            if item_id and statement.get("item_id") != item_id:
                self.errors.append(f"{prefix}: item_id does not match {item_id}")

            text = statement.get("text")
            if isinstance(text, str):
                normalized_text = text.strip().lower()
                if normalized_text.startswith(STATEMENT_TEXT_FORBIDDEN_PREFIXES):
                    self.errors.append(f"{prefix}: text must not be agent retelling of the source")
                if contains_redaction_placeholder(text):
                    self.errors.append(f"{prefix}: text contains inline redaction placeholder")
            elif "text" in statement:
                self.errors.append(f"{prefix}: text must be a string")

            excerpt = statement.get("excerpt")
            if isinstance(excerpt, str) and contains_redaction_placeholder(excerpt):
                self.errors.append(f"{prefix}: excerpt contains inline redaction placeholder")

            artifact = statement.get("artifact")
            if artifact and not (path.parent / artifact).exists():
                self.errors.append(f"{prefix}: artifact does not exist: {artifact}")

            self.add_value_errors(prefix, statement)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a project knowledge corpus layout.")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root containing corpus.yml, catalog.yml and data/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return Validator(Path(args.root)).validate()


if __name__ == "__main__":
    sys.exit(main())
