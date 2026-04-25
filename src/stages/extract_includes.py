"""Стадия: извлечение #include-директив и построение include-графа.

Для каждого файла находит #include-директивы, пытается резолвить пути,
сохраняет все попытки резолва в include_resolution_attempts.

Детектор: regex (HIGH confidence для самой директивы).
Confidence резолва:
  - HIGH:   файл найден однозначно (один кандидат)
  - MEDIUM: файл найден среди нескольких кандидатов
  - LOW:    файл не найден ни в одном из search_dirs

API:
    from src.stages.extract_includes import extract_includes
    result = extract_includes(source_root, db_path, run_id)

CLI:
    ./.venv/bin/python -m src.stages.extract_includes \\
        --source-dir <path> --db <path> [--run-id <int>] [-v]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click
import structlog

from src.db.schema import create_run, get_db, init_db
from src.utils import get_raw_context, read_lines

log = structlog.get_logger(__name__)

# Регексп для #include-директив
_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*(?P<angled><(?P<angled_path>[^>]+)>|"(?P<quoted_path>[^"]+)")',
    re.MULTILINE,
)

# Стандартные директории поиска заголовков (системные, для резолва)
_SYSTEM_INCLUDE_DIRS: list[str] = [
    "/usr/include",
    "/usr/local/include",
]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _resolve_include(
    include_path: str,
    include_type: str,
    source_file: Path,
    source_root: Path,
    extra_search_dirs: list[Path],
) -> tuple[list[tuple[str, Path | None]], Path | None]:
    """Попытаться разрешить include-путь.

    Returns:
        attempts: [(candidate_path_str, resolved_path_or_None), ...]
        best:     Path если разрешено, иначе None
    """
    search_dirs: list[Path] = []

    if include_type == "quoted":
        # Сначала ищем относительно исходного файла
        search_dirs.append(source_file.parent)

    # Затем корень проекта и все его поддиректории первого уровня
    search_dirs.append(source_root)
    for subdir in source_root.iterdir():
        if subdir.is_dir():
            search_dirs.append(subdir)

    # Дополнительные пути (переданные явно)
    search_dirs.extend(extra_search_dirs)

    # Системные пути для angled-include
    if include_type == "angled":
        for sys_dir in _SYSTEM_INCLUDE_DIRS:
            p = Path(sys_dir)
            if p.is_dir():
                search_dirs.append(p)

    attempts: list[tuple[str, Path | None]] = []
    best: Path | None = None

    for search_dir in search_dirs:
        candidate = (search_dir / include_path).resolve()
        candidate_str = str(search_dir / include_path)
        if candidate.is_file():
            attempts.append((candidate_str, candidate))
            if best is None:
                best = candidate
        else:
            attempts.append((candidate_str, None))

    # Убираем дубли (один и тот же абсолютный путь)
    seen: set[str] = set()
    deduped: list[tuple[str, Path | None]] = []
    for cand_str, resolved in attempts:
        key = str(resolved) if resolved else cand_str
        if key not in seen:
            seen.add(key)
            deduped.append((cand_str, resolved))

    return deduped, best


def _get_file_id(conn, run_id: int, rel_path: str) -> int | None:
    row = conn.execute(
        "SELECT file_id FROM files WHERE run_id = ? AND path = ?",
        (run_id, rel_path),
    ).fetchone()
    return row["file_id"] if row else None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def extract_includes(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    extra_search_dirs: list[Path] | None = None,
    logger=None,
) -> dict:
    """Извлечь #include-директивы из всех файлов, записать в БД.

    Args:
        source_root:       корень дерева исходников
        db_path:           путь к SQLite
        run_id:            ID прогона
        extra_search_dirs: дополнительные директории для резолва
        logger:            опциональный structlog-логгер

    Returns:
        {stage, status, count, resolved, unresolved, errors, elapsed_sec}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    count = 0
    resolved_count = 0
    unresolved_count = 0
    extra = extra_search_dirs or []

    with get_db(db_path) as conn:
        # Загрузить реестр файлов текущего прогона
        file_rows = conn.execute(
            "SELECT file_id, path, absolute_path FROM files WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        # Индексы для быстрого поиска
        path_to_id: dict[str, int] = {
            str(Path(r["absolute_path"]).resolve()): r["file_id"]
            for r in file_rows
        }

        for row in file_rows:
            file_id: int = row["file_id"]
            abs_path = Path(row["absolute_path"])
            rel_path: str = row["path"]

            try:
                lines = read_lines(abs_path)
            except OSError as exc:
                errors.append({"stage": "extract_includes", "file": rel_path, "error": str(exc)})
                continue

            content = "".join(lines)

            for m in _INCLUDE_RE.finditer(content):
                # Определить строку (1-based)
                line_number = content[: m.start()].count("\n") + 1

                if m.group("angled_path"):
                    include_path = m.group("angled_path")
                    include_type = "angled"
                else:
                    include_path = m.group("quoted_path")
                    include_type = "quoted"

                raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be = get_raw_context(
                    abs_path, line_number
                )

                attempts, best_path = _resolve_include(
                    include_path, include_type, abs_path, source_root, extra
                )

                resolved_file_id: int | None = None
                is_resolved = 0
                if best_path is not None:
                    resolved_file_id = path_to_id.get(str(best_path.resolve()))
                    is_resolved = 1

                # Confidence резолва
                resolved_attempts = [a for a in attempts if a[1] is not None]
                if not resolved_attempts:
                    confidence = "LOW"
                    confidence_reason = "include path not found in any search dir"
                elif len(resolved_attempts) > 1:
                    confidence = "MEDIUM"
                    confidence_reason = f"multiple candidates ({len(resolved_attempts)}), first used"
                else:
                    confidence = "HIGH"
                    confidence_reason = "unique resolution"

                try:
                    cur = conn.execute(
                        """
                        INSERT INTO includes (
                            run_id, source_file_id, line_number,
                            include_path, include_type,
                            resolved_file_id, is_resolved,
                            detector, confidence, confidence_reason,
                            raw_context,
                            raw_context_line_start, raw_context_line_end,
                            raw_context_byte_start, raw_context_byte_end
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id, file_id, line_number,
                            include_path, include_type,
                            resolved_file_id, is_resolved,
                            "regex", confidence, confidence_reason,
                            raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be,
                        ),
                    )
                    include_id = cur.lastrowid
                    count += 1
                    if is_resolved:
                        resolved_count += 1
                    else:
                        unresolved_count += 1

                    # Записать все попытки резолва
                    for cand_str, resolved_path in attempts:
                        conn.execute(
                            """
                            INSERT INTO include_resolution_attempts
                                (include_id, candidate_path, search_dir, resolved)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                include_id,
                                cand_str,
                                str(Path(cand_str).parent),
                                1 if resolved_path else 0,
                            ),
                        )
                except Exception as exc:
                    errors.append({
                        "stage": "extract_includes",
                        "file": rel_path,
                        "error": str(exc),
                    })
                    lg.warning("include_insert_error", file=rel_path, error=str(exc))

        conn.commit()

    elapsed = time.monotonic() - t0
    lg.info(
        "extract_includes_done",
        count=count,
        resolved=resolved_count,
        unresolved=unresolved_count,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "extract_includes",
        "status": "ok" if not errors else "partial",
        "count": count,
        "resolved": resolved_count,
        "unresolved": unresolved_count,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="extract-includes")
@click.option("--source-dir", "-s", required=True, type=click.Path(exists=True))
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--run-id", "run_id", type=int, default=None)
@click.option(
    "--include-dir", "-I", "extra_dirs", multiple=True, type=click.Path(),
    help="Дополнительная директория поиска заголовков (можно указать несколько)",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(
    source_dir: str,
    db_path: str,
    run_id: int | None,
    extra_dirs: tuple[str, ...],
    verbose: bool,
) -> None:
    """Извлечь #include-директивы и построить include-граф."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if verbose
            else structlog.processors.JSONRenderer(),
        ]
    )

    conn = init_db(db_path)
    if run_id is None:
        run_id = create_run(conn, source_dir, db_path)
        click.echo(f"Создан прогон: run_id={run_id}", err=True)
    conn.close()

    extra = [Path(d) for d in extra_dirs]
    result = extract_includes(
        Path(source_dir), Path(db_path), run_id,
        extra_search_dirs=extra,
    )
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
