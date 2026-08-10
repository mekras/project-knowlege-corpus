#!/usr/bin/env python3
"""Запретить скомпилированные Python-артефакты в исходниках пакета APM."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


BYTECODE_SUFFIXES = {".pyc", ".pyo"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Проверить исходники пакета APM на Python-байткод.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".apm")],
        help="Каталоги или файлы исходников пакета. По умолчанию .apm.",
    )
    return parser.parse_args()


def relative(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def find_artifacts(path: Path) -> list[Path]:
    if path.is_file() or path.is_symlink():
        return [path] if path.name == "__pycache__" or path.suffix in BYTECODE_SUFFIXES else []

    findings: list[Path] = []
    for directory, subdirectories, files in os.walk(path, followlinks=False):
        current = Path(directory)
        if "__pycache__" in subdirectories:
            findings.append(current / "__pycache__")
            subdirectories.remove("__pycache__")
        findings.extend(
            current / name
            for name in files
            if name == "__pycache__" or Path(name).suffix in BYTECODE_SUFFIXES
        )
    return findings


def main() -> int:
    args = parse_args()
    missing = [str(path) for path in args.paths if not path.exists()]
    if missing:
        print(f"Пути не найдены: {', '.join(missing)}", file=sys.stderr)
        return 2

    findings = sorted(
        {artifact.resolve() for path in args.paths for artifact in find_artifacts(path)},
    )
    if findings:
        print(
            "В исходниках пакета APM найдены скомпилированные Python-артефакты:",
            file=sys.stderr,
        )
        for artifact in findings:
            print(f"  - {relative(artifact)}", file=sys.stderr)
        print(
            "Удалите артефакты и запускайте Python-проверки с "
            "PYTHONDONTWRITEBYTECODE=1.",
            file=sys.stderr,
        )
        return 1

    print("Скомпилированных Python-артефактов в исходниках пакета APM нет.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
