"""Оркестратор полного цикла анализа C-кода.

Принимает дерево исходных текстов и опциональное имя файла БД.
Если имя БД не задано — генерирует его из имени каталога и текущей даты/времени.

Последовательность стадий:
  1. init_db        — создать схему БД
  2. discover_files — инвентаризировать файлы
  3. extract_includes      — include-граф
  4. extract_entities      — сущности (ctags)
    5. extract_types         — typedef-цепочки и uses типов (без локалов)
    6. extract_comments      — комментарии и привязка к сущностям
    7. extract_preprocessor  — #define / #ifdef-регионы
    8. extract_usages        — reference_candidates (cscope + regex)
    9. reconcile             — сверка детекторов, confidence

Каждая стадия логирует свой вывод. Оркестратор ведёт общий журнал с:
  - таймингом каждой стадии
  - количеством ошибок
  - запуском внешних инструментов (через structlog)
  - итоговым summary в JSON

API:
    from src.orchestrator import run_analysis
    result = run_analysis(source_root, db_path=None)

CLI:
    ./.venv/bin/python -m src.orchestrator <source_dir> [--db <path>]
        [--skip <stage>] [--no-cscope] [-v]
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click
import structlog

from src.db.schema import create_run, finish_run, init_db
from src.stages.discover_files import discover_files
from src.stages.extract_comments import extract_comments
from src.stages.extract_entities import extract_entities
from src.stages.extract_includes import extract_includes
from src.stages.extract_preprocessor import extract_preprocessor
from src.stages.extract_types import extract_types
from src.stages.extract_usages import extract_usages
from src.stages.reconcile import reconcile

log = structlog.get_logger(__name__)

PIPELINE_VERSION = "1.0.0"

# Порядок стадий (name → callable)
_STAGE_ORDER = [
    "discover_files",
    "extract_includes",
    "extract_entities",
    "extract_types",
    "extract_comments",
    "extract_preprocessor",
    "extract_usages",
    "reconcile",
]


# ---------------------------------------------------------------------------
# Генерация имени БД
# ---------------------------------------------------------------------------

def _auto_db_name(source_root: Path, output_dir: Path) -> Path:
    """Сгенерировать имя файла БД: <dirname>_<YYYYMMDD_HHMMSS>.db"""
    dirname = source_root.resolve().name
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{dirname}_{ts}.db"


# ---------------------------------------------------------------------------
# Вспомогательный логгер для внешних инструментов
# ---------------------------------------------------------------------------

def _make_stage_logger(stage_name: str):
    return structlog.get_logger(stage_name)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def run_analysis(
    source_root: Path,
    db_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    skip_stages: list[str] | None = None,
    use_cscope: bool = True,
    extra_include_dirs: list[Path] | None = None,
    verbose: bool = False,
    logger=None,
) -> dict:
    """Запустить полный пайплайн анализа C-кода.

    Args:
        source_root:        корень дерева исходников
        db_path:            путь к БД (None → авто-генерация)
        output_dir:         директория для авто-созданной БД (default: CWD)
        skip_stages:        список имён стадий для пропуска
        use_cscope:         использовать cscope в extract_usages
        extra_include_dirs: дополнительные пути для резолва include
        verbose:            подробный вывод в лог
        logger:             опциональный structlog-логгер

    Returns:
        {
          run_id, db_path, source_root,
          pipeline_version, stages, all_errors,
                                        total: {files, entities, references, comments, includes, call_sites, type_aliases, type_resolutions, type_uses},
          elapsed_sec, status
        }
    """
    lg = logger or log
    t0 = time.monotonic()

    source_root = source_root.resolve()
    out_dir = (output_dir or Path(".")).resolve()

    if db_path is None:
        db_path = _auto_db_name(source_root, out_dir)
        lg.info("db_name_auto_generated", db_path=str(db_path))

    skip = set(skip_stages or [])
    extra_includes = extra_include_dirs or []

    lg.info(
        "pipeline_start",
        source_root=str(source_root),
        db_path=str(db_path),
        pipeline_version=PIPELINE_VERSION,
        verbose=verbose,
        skip=sorted(skip),
    )

    # ------------------------------------------------------------------
    # Инициализация БД и создание прогона
    # ------------------------------------------------------------------
    conn = init_db(db_path)
    run_id = create_run(conn, source_root, db_path)
    conn.close()

    lg.info("run_created", run_id=run_id)

    completed_stages: list[str] = []
    all_errors: list[dict] = []
    stage_results: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Выполнение стадий
    # ------------------------------------------------------------------
    def run_stage(name: str, fn, **kwargs):
        nonlocal completed_stages, all_errors
        if name in skip:
            lg.info("stage_skipped", stage=name)
            return {}
        lg.info("stage_start", stage=name)
        t_stage = time.monotonic()
        try:
            result = fn(**kwargs)
        except Exception as exc:
            result = {
                "stage": name,
                "status": "error",
                "error": str(exc),
                "elapsed_sec": round(time.monotonic() - t_stage, 2),
            }
            lg.error("stage_failed", stage=name, error=str(exc))
            all_errors.append({"stage": name, "error": str(exc)})
        else:
            stage_errors = result.get("errors", [])
            all_errors.extend(stage_errors)
            lg.info(
                "stage_done",
                stage=name,
                status=result.get("status"),
                elapsed_sec=result.get("elapsed_sec"),
                errors=len(stage_errors),
            )
        completed_stages.append(name)
        stage_results[name] = result
        return result

    run_stage(
        "discover_files",
        discover_files,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        logger=_make_stage_logger("discover_files"),
    )
    run_stage(
        "extract_includes",
        extract_includes,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        extra_search_dirs=extra_includes,
        logger=_make_stage_logger("extract_includes"),
    )
    run_stage(
        "extract_entities",
        extract_entities,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        logger=_make_stage_logger("extract_entities"),
    )
    run_stage(
        "extract_types",
        extract_types,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        logger=_make_stage_logger("extract_types"),
    )
    run_stage(
        "extract_comments",
        extract_comments,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        logger=_make_stage_logger("extract_comments"),
    )
    run_stage(
        "extract_preprocessor",
        extract_preprocessor,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        logger=_make_stage_logger("extract_preprocessor"),
    )
    run_stage(
        "extract_usages",
        extract_usages,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        use_cscope=use_cscope,
        logger=_make_stage_logger("extract_usages"),
    )
    run_stage(
        "reconcile",
        reconcile,
        source_root=source_root,
        db_path=db_path,
        run_id=run_id,
        logger=_make_stage_logger("reconcile"),
    )

    # ------------------------------------------------------------------
    # Завершение прогона: обновить analysis_runs
    # ------------------------------------------------------------------
    conn2 = init_db(db_path)
    finish_run(conn2, run_id, completed_stages, all_errors)

    # Читаем итоговую статистику из БД
    def _count(table: str) -> int:
        row = conn2.execute(
            f"SELECT COUNT(*) FROM {table} WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row[0] if row else 0

    totals = {
        "files":      _count("files"),
        "entities":   _count("entities"),
        "references": _count("reference_candidates"),
        "call_sites": _count("call_sites"),
        "type_aliases": _count("type_aliases"),
        "type_resolutions": _count("type_resolutions"),
        "type_uses": _count("type_uses"),
        "comments":   _count("comments"),
        "includes":   _count("includes"),
        "regions":    _count("conditional_regions"),
        "symbols":    _count("preprocessor_symbols"),
    }

    # Confidence distribution для entities
    confidence_dist: dict[str, int] = {}
    for row in conn2.execute(
        "SELECT confidence, COUNT(*) as cnt FROM entities WHERE run_id = ? GROUP BY confidence",
        (run_id,),
    ).fetchall():
        confidence_dist[row["confidence"]] = row["cnt"]

    conn2.close()

    elapsed = time.monotonic() - t0
    status = "ok" if not all_errors else "partial"

    summary = {
        "run_id":            run_id,
        "db_path":           str(db_path),
        "source_root":       str(source_root),
        "pipeline_version":  PIPELINE_VERSION,
        "stages_completed":  completed_stages,
        "total":             totals,
        "confidence_distribution": confidence_dist,
        "all_errors":        all_errors,
        "elapsed_sec":       round(elapsed, 2),
        "status":            status,
    }

    lg.info(
        "pipeline_done",
        run_id=run_id,
        db=str(db_path),
        elapsed_sec=round(elapsed, 2),
        status=status,
        total_entities=totals["entities"],
        total_errors=len(all_errors),
    )

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="analyze")
@click.argument("source_dir", type=click.Path(exists=True))
@click.option(
    "--db", "db_path", default=None, type=click.Path(),
    help="Путь к файлу БД (авто-генерируется если не задан)",
)
@click.option(
    "--output-dir", default=".", type=click.Path(),
    help="Директория для авто-созданной БД",
)
@click.option(
    "--skip", "skip_stages", multiple=True,
    type=click.Choice(_STAGE_ORDER),
    help="Пропустить стадию (можно указать несколько)",
)
@click.option(
    "--no-cscope", "no_cscope", is_flag=True, default=False,
    help="Отключить cscope в extract_usages",
)
@click.option(
    "--include-dir", "-I", "extra_dirs", multiple=True, type=click.Path(),
    help="Дополнительная директория поиска заголовков",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(
    source_dir: str,
    db_path: str | None,
    output_dir: str,
    skip_stages: tuple[str, ...],
    no_cscope: bool,
    extra_dirs: tuple[str, ...],
    verbose: bool,
) -> None:
    """Запустить полный пайплайн анализа C-кода.

    \b
    Примеры:
      # Полный прогон с авто-именем БД
      ./.venv/bin/python -m src.orchestrator sample/seL4 -v

      # Сохранить БД в конкретный файл
      ./.venv/bin/python -m src.orchestrator sample/seL4 --db ./out/myproject.db

      # Пропустить медленную стадию usages
      ./.venv/bin/python -m src.orchestrator sample/seL4 --skip extract_usages
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if verbose
            else structlog.processors.JSONRenderer(),
        ]
    )

    result = run_analysis(
        source_root=Path(source_dir),
        db_path=Path(db_path) if db_path else None,
        output_dir=Path(output_dir),
        skip_stages=list(skip_stages),
        use_cscope=not no_cscope,
        extra_include_dirs=[Path(d) for d in extra_dirs],
        verbose=verbose,
    )

    # Всегда выводить summary в stdout (машиночитаемый JSON)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()  # pyright: ignore[reportCallIssue]
