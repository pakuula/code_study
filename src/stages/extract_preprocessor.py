"""Стадия: анализ препроцессорных директив.

Извлекает:
  - #define / #undef → таблица preprocessor_symbols
  - #if / #ifdef / #ifndef / #elif / #else / #endif → таблица conditional_regions
  - include-guards (паттерн #ifndef FOO_H / #define FOO_H) → помечает как include_guard

После извлечения conditional_regions — связывает каждую сущность из entities
с наименьшим охватывающим регионом через entity_presence_conditions.

API:
    from src.stages.extract_preprocessor import extract_preprocessor
    result = extract_preprocessor(source_root, db_path, run_id)

CLI:
    ./.venv/bin/python -m src.stages.extract_preprocessor \\
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

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Регекспы
# ---------------------------------------------------------------------------

_DIRECTIVE_RE = re.compile(
    r"^\s*#\s*(?P<directive>"
    r"define|undef|ifdef|ifndef|if\b|elif|else|endif"
    r")"
    r"(?:\s+(?P<rest>.+))?",
    re.MULTILINE,
)

# Паттерн include guard: #ifndef FOO_H / #define FOO_H
_INCLUDE_GUARD_RE = re.compile(r"^[A-Z_][A-Z0-9_]*_H(?:PP)?$")

# Разбор function-like макроса: #define NAME(a, b) body
_DEFINE_FUNC_RE = re.compile(
    r"^(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^)]*)\)\s*(?P<value>.*)"
)
# Разбор object-like макроса: #define NAME value
_DEFINE_OBJ_RE = re.compile(
    r"^(?P<name>[A-Za-z_]\w*)(?:\s+(?P<value>.*))?$"
)


# ---------------------------------------------------------------------------
# Парсинг одного файла
# ---------------------------------------------------------------------------

def _parse_file(
    content: str,
) -> tuple[list[dict], list[dict]]:
    """
    Returns:
        symbols:  list of preprocessor_symbol dicts
        regions:  list of conditional_region dicts (без parent_region_id, без region_id)
    """
    symbols: list[dict] = []

    # ------------------------------------------------------------------
    # Стек для построения дерева условных регионов
    # ------------------------------------------------------------------
    # Каждый элемент стека: dict с полями directive/condition/line_start/depth
    stack: list[dict] = []
    regions_raw: list[dict] = []   # без parent_region_id
    depth = 0

    lines = content.splitlines()
    # Детектировать include guard (первый ifndef + define в начале файла)
    _include_guard_candidates: list[str] = []

    for lineno, line in enumerate(lines, start=1):
        m = _DIRECTIVE_RE.match(line)
        if not m:
            continue

        directive = m.group("directive").lower()
        rest = (m.group("rest") or "").strip()

        # ------------------------------------------------------------------
        # Условные регионы
        # ------------------------------------------------------------------
        if directive in ("if", "ifdef", "ifndef"):
            condition = rest
            stack.append({
                "directive": directive,
                "condition": condition,
                "line_start": lineno,
                "depth": depth,
                "parent_idx": len(regions_raw),  # будет заполнено при закрытии
            })
            regions_raw.append({
                "directive": directive,
                "condition": condition,
                "line_start": lineno,
                "line_end": None,
                "depth": depth,
                "_stack_index": len(regions_raw),
            })
            depth += 1

            if directive == "ifndef":
                _include_guard_candidates.append(rest)

        elif directive in ("elif", "else"):
            if stack:
                # Закрыть текущий регион
                current = stack[-1]
                idx = current.get("parent_idx", 0)
                if idx < len(regions_raw) and regions_raw[idx]["line_end"] is None:
                    regions_raw[idx]["line_end"] = lineno - 1
                # Открыть новый регион (elif/else продолжение)
                new_region = {
                    "directive": directive,
                    "condition": rest if directive == "elif" else None,
                    "line_start": lineno,
                    "line_end": None,
                    "depth": max(0, depth - 1),
                    "_stack_index": len(regions_raw),
                }
                regions_raw.append(new_region)
                stack[-1] = {
                    "directive": directive,
                    "condition": new_region["condition"],
                    "line_start": lineno,
                    "depth": max(0, depth - 1),
                    "parent_idx": len(regions_raw) - 1,
                }

        elif directive == "endif":
            if stack:
                current = stack.pop()
                depth = max(0, depth - 1)
                idx = current.get("parent_idx", 0)
                if idx < len(regions_raw) and regions_raw[idx]["line_end"] is None:
                    regions_raw[idx]["line_end"] = lineno

        # ------------------------------------------------------------------
        # Символы (#define / #undef)
        # ------------------------------------------------------------------
        elif directive == "define":
            # function-like?
            fm = _DEFINE_FUNC_RE.match(rest)
            if fm:
                name = fm.group("name")
                params_raw = [p.strip() for p in fm.group("params").split(",") if p.strip()]
                value = fm.group("value").strip()
                sym_type = "define"
                is_function_like = 1
            else:
                om = _DEFINE_OBJ_RE.match(rest)
                if not om:
                    continue
                name = om.group("name")
                value = (om.group("value") or "").strip()
                params_raw = []
                sym_type = "define"
                is_function_like = 0

                # include guard?
                if name in _include_guard_candidates:
                    sym_type = "include_guard"

            symbols.append({
                "name": name,
                "symbol_type": sym_type,
                "line_number": lineno,
                "value": value or None,
                "params": json.dumps(params_raw) if params_raw else None,
                "is_function_like": is_function_like,
            })

        elif directive == "undef":
            name = rest.split()[0] if rest else ""
            if name:
                symbols.append({
                    "name": name,
                    "symbol_type": "undef",
                    "line_number": lineno,
                    "value": None,
                    "params": None,
                    "is_function_like": 0,
                })

    # Закрыть незакрытые регионы (на случай отсутствующих endif)
    for item in regions_raw:
        if item["line_end"] is None:
            item["line_end"] = len(lines)

    return symbols, regions_raw


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def extract_preprocessor(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    logger=None,
) -> dict:
    """Извлечь препроцессорные директивы из всех файлов.

    Returns:
        {stage, status, symbols, regions, epc_linked, errors, elapsed_sec}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    sym_count = 0
    region_count = 0
    epc_count = 0

    with get_db(db_path) as conn:
        file_rows = conn.execute(
            "SELECT file_id, path, absolute_path FROM files WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        for row in file_rows:
            file_id: int = row["file_id"]
            abs_path = Path(row["absolute_path"])
            rel_path: str = row["path"]

            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append({"stage": "extract_preprocessor", "file": rel_path, "error": str(exc)})
                continue

            symbols, regions_raw = _parse_file(content)

            # Вставить conditional_regions (без parent_region_id на первом проходе)
            region_id_map: dict[int, int] = {}  # _stack_index → region_id в БД
            for reg in regions_raw:
                try:
                    cur = conn.execute(
                        """
                        INSERT INTO conditional_regions
                            (run_id, file_id, directive, condition,
                             line_start, line_end, depth)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id, file_id,
                            reg["directive"], reg.get("condition"),
                            reg["line_start"], reg.get("line_end"),
                            reg["depth"],
                        ),
                    )
                    region_id_map[reg["_stack_index"]] = cur.lastrowid
                    region_count += 1
                except Exception as exc:
                    errors.append({
                        "stage": "extract_preprocessor",
                        "file": rel_path,
                        "error": str(exc),
                    })

            # Вставить preprocessor_symbols
            for sym in symbols:
                try:
                    conn.execute(
                        """
                        INSERT INTO preprocessor_symbols
                            (run_id, file_id, name, symbol_type, line_number,
                             value, params, is_function_like)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id, file_id,
                            sym["name"], sym["symbol_type"], sym["line_number"],
                            sym.get("value"), sym.get("params"),
                            sym["is_function_like"],
                        ),
                    )
                    sym_count += 1
                except Exception as exc:
                    errors.append({
                        "stage": "extract_preprocessor",
                        "file": rel_path,
                        "error": str(exc),
                    })

        conn.commit()

        # ------------------------------------------------------------------
        # entity_presence_conditions:
        # для каждой сущности найти наименьший охватывающий conditional_region
        # ------------------------------------------------------------------
        entities = conn.execute(
            "SELECT entity_id, file_id, line_start FROM entities WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        for ent in entities:
            ent_line = ent["line_start"] or 0
            # Найти регион с максимальным depth, который содержит ent_line
            containing = conn.execute(
                """
                SELECT region_id, condition, directive
                FROM conditional_regions
                WHERE run_id = ? AND file_id = ?
                  AND line_start <= ? AND (line_end IS NULL OR line_end >= ?)
                ORDER BY depth DESC
                LIMIT 1
                """,
                (run_id, ent["file_id"], ent_line, ent_line),
            ).fetchone()

            if containing:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO entity_presence_conditions
                            (entity_id, conditional_region_id, condition_text)
                        VALUES (?, ?, ?)
                        """,
                        (
                            ent["entity_id"],
                            containing["region_id"],
                            containing["condition"],
                        ),
                    )
                    epc_count += 1
                except Exception:
                    pass

        conn.commit()

    elapsed = time.monotonic() - t0
    lg.info(
        "extract_preprocessor_done",
        symbols=sym_count,
        regions=region_count,
        epc_linked=epc_count,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "extract_preprocessor",
        "status": "ok" if not errors else "partial",
        "symbols": sym_count,
        "regions": region_count,
        "epc_linked": epc_count,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="extract-preprocessor")
@click.option("--source-dir", "-s", required=True, type=click.Path(exists=True))
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--run-id", "run_id", type=int, default=None)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(source_dir: str, db_path: str, run_id: int | None, verbose: bool) -> None:
    """Извлечь препроцессорные директивы (#define, #ifdef и т.п.)."""
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

    result = extract_preprocessor(Path(source_dir), Path(db_path), run_id)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
