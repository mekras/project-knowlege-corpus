#!/usr/bin/env python3
"""Regression tests for the portable transcription result verifier."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".apm" / "skills" / "kc-transcription" / "scripts" / "validate-transcription-result.py"


def run(item_dir: Path, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(item_dir), *arguments],
        capture_output=True,
        text=True,
    )
    if result.returncode != expected:
        raise AssertionError(f"Ожидался код {expected}, получен {result.returncode}: {result.stderr}")
    return result


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        item_dir = Path(temporary) / "item"
        item_dir.mkdir()
        temporary_media = item_dir / "recording.tmp.mp4"
        temporary_media.write_bytes(b"media")
        persistent_media = item_dir / "recording.local.mp4"
        persistent_media.write_bytes(b"media")

        missing = run(item_dir, "--media", temporary_media.name, "--cleanup", expected=2)
        if "непустой transcript.txt" not in missing.stderr or not temporary_media.exists():
            raise AssertionError("Очистка до появления расшифровки должна быть запрещена.")

        (item_dir / "transcript.txt").write_text("Сырая расшифровка.\n", encoding="utf-8")
        preview = run(item_dir, "--media", temporary_media.name)
        if json.loads(preview.stdout)["cleanup_candidates"] != [temporary_media.name] or not temporary_media.exists():
            raise AssertionError("Пробный запуск не должен удалять временное медиа.")

        cleanup = run(item_dir, "--media", temporary_media.name, "--cleanup")
        if json.loads(cleanup.stdout)["removed"] != [temporary_media.name] or temporary_media.exists():
            raise AssertionError("Явная очистка не удалила проверенное временное медиа.")

        temporary_transcript = item_dir / "2026-09-02.tmp.txt"
        temporary_transcript.write_text("Временная сырая расшифровка.\n", encoding="utf-8")
        transcript_cleanup = run(
            item_dir,
            "--transcript",
            temporary_transcript.name,
            "--media",
            temporary_transcript.name,
            "--cleanup",
        )
        transcript_cleanup_data = json.loads(transcript_cleanup.stdout)
        if (
            transcript_cleanup_data["status"] != "temporary_transcript_cleaned"
            or transcript_cleanup_data["transcript"] != temporary_transcript.name
            or transcript_cleanup_data["removed"] != [temporary_transcript.name]
            or temporary_transcript.exists()
        ):
            raise AssertionError("Временная расшифровка с проектным именем не очистилась.")

        persistent = run(item_dir, "--media", persistent_media.name, "--cleanup", expected=2)
        if "*.tmp.*" not in persistent.stderr or not persistent_media.exists():
            raise AssertionError("Постоянное локальное медиа не должно удаляться.")

    print("Проверки договора расшифровки прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
