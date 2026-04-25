"""Общие вспомогательные функции для всех стадий анализа.

Не содержит зависимостей от конкретных проектов (project-agnostic).
Запуск: модуль только для импорта, не исполняется напрямую.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

# Расширения файлов, которые анализируем
C_EXTENSIONS: frozenset[str] = frozenset({
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hxx", ".hh",
})
HEADER_EXTENSIONS: frozenset[str] = frozenset({
    ".h", ".hpp", ".hxx", ".hh",
})


# ---------------------------------------------------------------------------
# Файловые утилиты
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Вычислить SHA-256 хэш файла (потоково, без загрузки в память)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_lines(path: Path) -> list[str]:
    """Прочитать строки файла с tolerant-обработкой кодировки."""
    return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def get_raw_context(
    path: Path,
    line_number: int,
    context_lines: int = 3,
) -> tuple[str, int, int, int, int]:
    """Вернуть ±context_lines строк вокруг line_number (1-based).

    Returns:
        (text, line_start, line_end, byte_start, byte_end)
        Все значения 1-based, byte-офсеты — от начала файла.
    """
    try:
        lines = read_lines(path)
        total = len(lines)
        line_start = max(1, line_number - context_lines)
        line_end = min(total, line_number + context_lines)
        encoded = [ln.encode("utf-8", errors="replace") for ln in lines]
        byte_start = sum(len(e) for e in encoded[: line_start - 1])
        byte_end = byte_start + sum(len(e) for e in encoded[line_start - 1 : line_end])
        text = "".join(lines[line_start - 1 : line_end])
        return text, line_start, line_end, byte_start, byte_end
    except Exception:
        return "", line_number, line_number, 0, 0


def line_byte_offset(lines_encoded: list[bytes], line_number: int) -> int:
    """Байтовый офсет начала строки line_number (1-based)."""
    return sum(len(e) for e in lines_encoded[: line_number - 1])


# ---------------------------------------------------------------------------
# Запуск внешних инструментов
# ---------------------------------------------------------------------------

def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 300,
    input_text: str | None = None,
) -> tuple[int, str, str]:
    """Запустить внешнюю команду.

    Returns:
        (returncode, stdout, stderr)
        returncode=-1: timeout; -2: not found; -3: other exception
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout ({timeout}s): {' '.join(cmd)}"
    except FileNotFoundError:
        return -2, "", f"Команда не найдена: {cmd[0]}"
    except Exception as exc:
        return -3, "", str(exc)


def tool_available(name: str) -> bool:
    """Проверить, доступна ли внешняя утилита в PATH."""
    rc, _, _ = run_command(["which", name], timeout=5)
    return rc == 0
