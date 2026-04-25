"""Стадия: извлечение кандидатов на использования сущностей (reference_candidates).

Двухпроходная стратегия:
  1. cscope (если доступен): строим БД, запрашиваем по каждому имени сущности.
     Детектор: 'cscope', confidence: 'MEDIUM'
  2. regex-проход по всем файлам: ищем все вхождения имён сущностей, классифицируем
     тип по контексту.
     Детектор: 'regex', confidence: 'LOW'

Классификация candidate_type по контексту (regex-эвристика):
  - После имени идёт '(' → call_candidate
  - Перед именем идёт #define/тип → type_reference_candidate
  - Иначе → read_write_candidate

access_kind, scope_distance, candidate_rank — заполняются на стадии reconcile.

API:
    from src.stages.extract_usages import extract_usages
    result = extract_usages(source_root, db_path, run_id)

CLI:
    ./.venv/bin/python -m src.stages.extract_usages \\
        --source-dir <path> --db <path> [--run-id <int>] [--no-cscope] [-v]
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click
import structlog

from src.db.schema import create_run, get_db, init_db
from src.utils import get_raw_context, run_command, tool_available

log = structlog.get_logger(__name__)

# Минимальная длина имени для поиска (избегаем однобуквенных имён)
_MIN_NAME_LEN = 2

# Тип-ключевые слова C (для классификации type_reference_candidate)
_C_TYPE_KEYWORDS = frozenset({
    "int", "char", "void", "short", "long", "float", "double",
    "unsigned", "signed", "struct", "union", "enum", "typedef",
    "const", "static", "extern", "inline", "restrict",
})


# ---------------------------------------------------------------------------
# cscope
# ---------------------------------------------------------------------------

def _build_cscope_db(source_root: Path, work_dir: Path) -> tuple[bool, str]:
    """Построить cscope.out в work_dir."""
    if not tool_available("cscope"):
        return False, "cscope not found in PATH"
    rc, _, stderr = run_command(
        ["cscope", "-b", "-q", "-R", "-s", str(source_root)],
        cwd=work_dir,
        timeout=600,
    )
    if rc not in (0, 1):  # cscope возвращает 0 или 1 при успехе
        return False, stderr
    if not (work_dir / "cscope.out").exists():
        return False, "cscope.out not created"
    return True, ""


def _query_cscope(name: str, work_dir: Path) -> list[tuple[str, str, int, str]]:
    """Запросить cscope: найти все использования символа name.

    Returns: [(file_path, function_name, line_number, text), ...]
    """
    # Тип 0: find all references to the C symbol
    rc, stdout, _ = run_command(
        ["cscope", "-d", "-f", "cscope.out", "-L0", name],
        cwd=work_dir,
        timeout=30,
    )
    if rc < 0 or not stdout.strip():
        return []

    results: list[tuple[str, str, int, str]] = []
    for line in stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        try:
            file_path, func_name, line_str, *rest = parts
            line_no = int(line_str)
            text = rest[0] if rest else ""
            results.append((file_path, func_name, line_no, text))
        except ValueError:
            continue
    return results


# ---------------------------------------------------------------------------
# Regex-проход
# ---------------------------------------------------------------------------

def _classify_candidate(
    line_text: str,
    name: str,
    col_start: int,
) -> tuple[str, str | None]:
    """Эвристически определить candidate_type и access_kind.

    Returns:
        (candidate_type, access_kind | None)
    """
    after = line_text[col_start + len(name) :].lstrip()
    before = line_text[:col_start].rstrip()

    # Вызов функции: имя идёт прямо перед '('
    if after.startswith("("):
        return "call_candidate", "call"

    # Расширение макроса: перед именем стоит #define или само в директиве
    if re.search(r"#\s*define\s*$", before) or re.search(r"#\s*(ifdef|ifndef|if)\s*$", before):
        return "macro_expansion_candidate", "macro_exp"

    # Использование как тип: имя предшествует идентификатору или '*' (typedef-like)
    if re.match(r"\s*\*?\s*[A-Za-z_]", after) and (
        bool(re.search(r"\b(typedef|struct|union|enum)\s*$", before))
        or before.rstrip().split()[-1:] in ([k] for k in _C_TYPE_KEYWORDS)
    ):
        return "type_reference_candidate", "type_ref"

    # Присвоение: имя слева от '='
    if re.match(r"\s*=\s*[^=]", after):
        return "read_write_candidate", "write"

    return "read_write_candidate", "read"


def _find_usages_regex(
    file_path: Path,
    names: set[str],
    file_id: int,
    run_id: int,
    source_root: Path,
) -> list[dict]:
    """Найти вхождения всех имён в файле через regex."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    records: list[dict] = []
    lines = content.splitlines()

    # Один проход — ищем все имена. Чтобы не делать N regex-ов, ищем по одному.
    # Для больших наборов имён это медленно, но надёжно.
    for name in names:
        if len(name) < _MIN_NAME_LEN:
            continue
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        for lineno, line in enumerate(lines, start=1):
            for m in pattern.finditer(line):
                col_start = m.start() + 1  # 1-based
                col_end = m.end() + 1

                ctype, access_kind = _classify_candidate(line, name, m.start())

                raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be = get_raw_context(
                    file_path, lineno
                )

                records.append({
                    "run_id": run_id,
                    "file_id": file_id,
                    "name": name,
                    "line_number": lineno,
                    "col_start": col_start,
                    "col_end": col_end,
                    "candidate_type": ctype,
                    "access_kind": access_kind,
                    "detector": "regex",
                    "confidence": "LOW",
                    "confidence_reason": "regex heuristic, no semantic context",
                    "raw_context": raw_ctx,
                    "raw_context_line_start": ctx_ls,
                    "raw_context_line_end": ctx_le,
                    "raw_context_byte_start": ctx_bs,
                    "raw_context_byte_end": ctx_be,
                })
    return records


def _resolve_entity_id(
    name: str,
    file_id: int,
    candidate_type: str,
    entities_by_name: dict[str, list[dict]],
) -> int | None:
    """Разрешить ссылку на сущность с учётом scope и типа кандидата.

    Ключевая цель: корректно обрабатывать file-level static переменные,
    чтобы ссылки в файле не уезжали в одноимённые глобальные/чужие записи.
    """
    candidates = entities_by_name.get(name, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["entity_id"]

    prefer_function = (candidate_type == "call_candidate")

    def _score(ent: dict) -> int:
        score = 0
        kind = ent.get("kind")
        scope = ent.get("scope")

        if prefer_function:
            score += 0 if kind == "function" else 40
        else:
            score += 0 if kind != "function" else 40
            if kind == "variable":
                score -= 5

        # Для static/local в том же файле — сильный приоритет.
        if ent.get("file_id") == file_id and scope in ("static", "local"):
            score -= 30
        elif ent.get("file_id") == file_id:
            score -= 15

        if scope in ("global", "extern"):
            score -= 2

        # Предпочитаем definition при прочих равных.
        score -= 3 if ent.get("is_definition") else 0
        score += 3 if ent.get("is_declaration") else 0

        return score

    ranked = sorted(candidates, key=lambda ent: (_score(ent), ent["entity_id"]))
    if len(ranked) > 1 and _score(ranked[0]) == _score(ranked[1]):
        return None
    return ranked[0]["entity_id"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def extract_usages(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    use_cscope: bool = True,
    logger=None,
) -> dict:
    """Извлечь кандидатов на использования сущностей.

    Args:
        source_root:  корень дерева исходников
        db_path:      путь к SQLite
        run_id:       ID прогона
        use_cscope:   использовать cscope (если доступен)
        logger:       опциональный structlog-логгер

    Returns:
        {stage, status, count, cscope_count, regex_count, errors, elapsed_sec}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    total_count = 0
    cscope_count = 0
    regex_count = 0

    with get_db(db_path) as conn:
        # Загрузить сущности текущего прогона
        entity_rows = conn.execute(
            """
            SELECT entity_id, name, kind, file_id, scope,
                   is_declaration, is_definition, line_start
            FROM entities
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()

        if not entity_rows:
            lg.warning("no_entities_found", run_id=run_id)
            return {
                "stage": "extract_usages",
                "status": "ok",
                "count": 0,
                "cscope_count": 0,
                "regex_count": 0,
                "errors": [],
                "elapsed_sec": 0.0,
            }

        # Уникальные имена сущностей (без слишком коротких)
        entity_names: set[str] = {
            r["name"] for r in entity_rows if len(r["name"]) >= _MIN_NAME_LEN
        }
        entities_by_name: dict[str, list[dict]] = {}
        for row in entity_rows:
            entities_by_name.setdefault(row["name"], []).append(dict(row))

        lg.info("extract_usages_start", entity_count=len(entity_names))

        # Загрузить файлы
        file_rows = conn.execute(
            "SELECT file_id, path, absolute_path FROM files WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        file_id_map: dict[str, int] = {
            str(Path(r["absolute_path"]).resolve()): r["file_id"]
            for r in file_rows
        }
        relpath_to_id: dict[str, int] = {
            r["path"]: r["file_id"] for r in file_rows
        }

        # ------------------------------------------------------------------
        # Проход 1: cscope
        # ------------------------------------------------------------------
        cscope_records: dict[tuple[int, int, str], dict] = {}  # (file_id, lineno, name) → record

        if use_cscope and tool_available("cscope"):
            with tempfile.TemporaryDirectory(prefix="canalysis_cscope_") as tmpdir:
                tmp_path = Path(tmpdir)
                ok, cscope_err = _build_cscope_db(source_root, tmp_path)
                if not ok:
                    lg.warning("cscope_build_failed", error=cscope_err)
                    errors.append({"stage": "extract_usages", "error": f"cscope: {cscope_err}"})
                else:
                    lg.info("cscope_db_built")
                    for name in entity_names:
                        hits = _query_cscope(name, tmp_path)
                        for (fpath, _func, lineno, text) in hits:
                            # Нормализовать путь к файлу
                            fpath_abs = str(
                                (source_root / fpath).resolve()
                                if not Path(fpath).is_absolute()
                                else Path(fpath).resolve()
                            )
                            file_id = file_id_map.get(fpath_abs)
                            if file_id is None:
                                continue  # файл вне нашего дерева

                            abs_file = Path(
                                conn.execute(
                                    "SELECT absolute_path FROM files WHERE file_id = ?",
                                    (file_id,),
                                ).fetchone()["absolute_path"]
                            )

                            raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be = get_raw_context(
                                abs_file, lineno
                            )

                            # Классифицировать по тексту строки из cscope
                            ctype, access_kind = _classify_candidate(text, name, 0)

                            key = (file_id, lineno, name)
                            cscope_records[key] = {
                                "run_id": run_id,
                                "file_id": file_id,
                                "name": name,
                                "line_number": lineno,
                                "candidate_type": ctype,
                                "access_kind": access_kind,
                                "resolved_entity_id": _resolve_entity_id(
                                    name,
                                    file_id,
                                    ctype,
                                    entities_by_name,
                                ),
                                "detector": "cscope",
                                "confidence": "MEDIUM",
                                "confidence_reason": "cscope cross-reference",
                                "raw_context": raw_ctx,
                                "raw_context_line_start": ctx_ls,
                                "raw_context_line_end": ctx_le,
                                "raw_context_byte_start": ctx_bs,
                                "raw_context_byte_end": ctx_be,
                            }

            # Вставить cscope-записи
            for rec in cscope_records.values():
                try:
                    conn.execute(
                        """
                        INSERT INTO reference_candidates (
                            run_id, file_id, name, line_number,
                            candidate_type, access_kind, resolved_entity_id,
                            detector, confidence, confidence_reason,
                            raw_context,
                            raw_context_line_start, raw_context_line_end,
                            raw_context_byte_start, raw_context_byte_end
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rec["run_id"], rec["file_id"], rec["name"],
                            rec["line_number"],
                            rec["candidate_type"], rec.get("access_kind"),
                            rec.get("resolved_entity_id"),
                            rec["detector"], rec["confidence"],
                            rec["confidence_reason"],
                            rec.get("raw_context"),
                            rec.get("raw_context_line_start"),
                            rec.get("raw_context_line_end"),
                            rec.get("raw_context_byte_start"),
                            rec.get("raw_context_byte_end"),
                        ),
                    )
                    cscope_count += 1
                    total_count += 1
                except Exception as exc:
                    errors.append({"stage": "extract_usages", "error": str(exc)})

        conn.commit()

        # ------------------------------------------------------------------
        # Проход 2: regex по всем файлам
        # Добавляем только те вхождения, которых нет от cscope (по ключу file+line+name)
        # ------------------------------------------------------------------
        cscope_keys = set(cscope_records.keys())

        for frow in file_rows:
            file_id: int = frow["file_id"]
            abs_file = Path(frow["absolute_path"])

            regex_recs = _find_usages_regex(
                abs_file, entity_names, file_id, run_id, source_root
            )

            for rec in regex_recs:
                key = (rec["file_id"], rec["line_number"], rec["name"])
                if key in cscope_keys:
                    continue  # уже покрыто cscope

                try:
                    conn.execute(
                        """
                        INSERT INTO reference_candidates (
                            run_id, file_id, name, line_number,
                            col_start, col_end,
                            candidate_type, access_kind,
                            resolved_entity_id,
                            detector, confidence, confidence_reason,
                            raw_context,
                            raw_context_line_start, raw_context_line_end,
                            raw_context_byte_start, raw_context_byte_end
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rec["run_id"], rec["file_id"], rec["name"],
                            rec["line_number"],
                            rec.get("col_start"), rec.get("col_end"),
                            rec["candidate_type"], rec.get("access_kind"),
                            _resolve_entity_id(
                                rec["name"],
                                rec["file_id"],
                                rec["candidate_type"],
                                entities_by_name,
                            ),
                            rec["detector"], rec["confidence"],
                            rec["confidence_reason"],
                            rec.get("raw_context"),
                            rec.get("raw_context_line_start"),
                            rec.get("raw_context_line_end"),
                            rec.get("raw_context_byte_start"),
                            rec.get("raw_context_byte_end"),
                        ),
                    )
                    regex_count += 1
                    total_count += 1
                except Exception as exc:
                    errors.append({"stage": "extract_usages", "error": str(exc)})

        conn.commit()

    elapsed = time.monotonic() - t0
    lg.info(
        "extract_usages_done",
        total=total_count,
        cscope=cscope_count,
        regex=regex_count,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "extract_usages",
        "status": "ok" if not errors else "partial",
        "count": total_count,
        "cscope_count": cscope_count,
        "regex_count": regex_count,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="extract-usages")
@click.option("--source-dir", "-s", required=True, type=click.Path(exists=True))
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--run-id", "run_id", type=int, default=None)
@click.option("--no-cscope", "no_cscope", is_flag=True, default=False,
              help="Отключить cscope, использовать только regex")
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(
    source_dir: str,
    db_path: str,
    run_id: int | None,
    no_cscope: bool,
    verbose: bool,
) -> None:
    """Извлечь кандидатов на использования сущностей (cscope + regex)."""
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

    result = extract_usages(
        Path(source_dir), Path(db_path), run_id,
        use_cscope=not no_cscope,
    )
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
