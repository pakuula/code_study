"""Стадия: инвентаризация файлов исходного кода.

Сканирует source_root рекурсивно, вносит записи в таблицу files.

API:
    from src.stages.discover_files import discover_files
    result = discover_files(source_root, db_path, run_id)

CLI:
    ./.venv/bin/python -m src.stages.discover_files \\
        --source-dir <path> --db <path> [--run-id <int>] [-v]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click
import structlog

from src.db.schema import create_run, get_db, init_db
from src.utils import C_EXTENSIONS, HEADER_EXTENSIONS, sha256_file

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def discover_files(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    logger=None,
) -> dict:
    """Просканировать source_root, записать файлы в таблицу files.

    Args:
        source_root: корень дерева исходных текстов
        db_path:     путь к файлу SQLite
        run_id:      ID текущего прогона (из analysis_runs)
        logger:      опциональный structlog-логгер

    Returns:
        {stage, status, count, errors, elapsed_sec}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    count = 0

    with get_db(db_path) as conn:
        for file_path in sorted(source_root.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in C_EXTENSIONS:
                continue

            rel_path = str(file_path.relative_to(source_root))
            is_header = 1 if file_path.suffix.lower() in HEADER_EXTENSIONS else 0

            try:
                size = file_path.stat().st_size
                sha = sha256_file(file_path)
            except OSError as exc:
                errors.append({"stage": "discover_files", "file": rel_path, "error": str(exc)})
                lg.warning("file_stat_error", file=rel_path, error=str(exc))
                continue

            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO files
                        (run_id, path, absolute_path, size_bytes, sha256, is_header)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, rel_path, str(file_path), size, sha, is_header),
                )
                count += 1
                lg.debug("file_added", path=rel_path, size=size)
            except Exception as exc:
                errors.append({"stage": "discover_files", "file": rel_path, "error": str(exc)})
                lg.warning("file_insert_error", file=rel_path, error=str(exc))

        conn.commit()

    elapsed = time.monotonic() - t0
    status = "ok" if not errors else "partial"
    lg.info(
        "discover_files_done",
        count=count,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "discover_files",
        "status": status,
        "count": count,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="discover-files")
@click.option(
    "--source-dir", "-s", required=True, type=click.Path(exists=True),
    help="Корень дерева исходных текстов",
)
@click.option(
    "--db", "db_path", required=True, type=click.Path(),
    help="Путь к файлу БД SQLite",
)
@click.option(
    "--run-id", "run_id", type=int, default=None,
    help="ID прогона (если уже создан оркестратором)",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(source_dir: str, db_path: str, run_id: int | None, verbose: bool) -> None:
    """Инвентаризация файлов исходного кода."""
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

    result = discover_files(Path(source_dir), Path(db_path), run_id)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
