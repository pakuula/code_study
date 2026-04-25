"""Стадия: извлечение сущностей C-кода.

Запускает universal-ctags с --output-format=json, парсит JSONL-вывод,
записывает сущности в таблицу entities.

Confidence:
  HIGH   — определение функции/переменной/типа (is_definition=1)
  MEDIUM — объявление/прототип, или сущность внутри условного региона
  LOW    — не удалось определить kind или scope

Детектор: 'ctags'

API:
    from src.stages.extract_entities import extract_entities
    result = extract_entities(source_root, db_path, run_id)

CLI:
    ./.venv/bin/python -m src.stages.extract_entities \\
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
from src.utils import get_raw_context, run_command, tool_available

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Маппинг ctags-kind → наш kind
# ---------------------------------------------------------------------------

_CTAGS_KIND_MAP: dict[str, str] = {
    # C-specific kinds (universal-ctags)
    "function":    "function",
    "prototype":   "function",     # декларация функции
    "variable":    "variable",
    "externvar":   "variable",
    "local":       "variable",
    "typedef":     "typedef",
    "struct":      "struct",
    "union":       "union",
    "enum":        "enum",
    "enumerator":  "enumerator",
    "macro":       "macro",
    "define":      "macro",
    "member":      "field",
    "field":       "field",
    "label":       "label",
    # fallback
    "header":      "variable",
}

_IS_DECLARATION_KINDS: frozenset[str] = frozenset({
    "prototype", "externvar",
})

# ctags scope/access → наш scope
_SCOPE_MAP: dict[str, str] = {
    "file":    "static",
    "static":  "static",
    "extern":  "extern",
    "local":   "local",
    "public":  "global",
    "global":  "global",
}


# ---------------------------------------------------------------------------
# Запуск ctags
# ---------------------------------------------------------------------------

def _run_ctags(source_root: Path) -> tuple[list[dict], str | None]:
    """Запустить ctags, вернуть список тегов и текст ошибки (или None)."""
    if not tool_available("ctags"):
        return [], "ctags not found in PATH"

    cmd = [
        "ctags",
        "--output-format=json",
        "--fields=+nKZSl",   # n=line, K=kind(full), Z=scope, S=signature, l=language
        "--extras=-F",       # отключить pseudo-tags
        "--languages=C",
        "-f", "-",           # вывод в stdout
        "-R",
        str(source_root),
    ]
    rc, stdout, stderr = run_command(cmd, cwd=source_root, timeout=300)
    if rc < 0:
        return [], stderr
    if rc != 0 and not stdout.strip():
        return [], stderr

    tags: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get("_type") == "tag":
                tags.append(obj)
        except json.JSONDecodeError:
            continue  # ctags иногда выводит non-JSON строки

    return tags, None


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _map_kind(ctags_kind: str) -> str:
    return _CTAGS_KIND_MAP.get(ctags_kind.lower(), "variable")


def _map_scope(ctags_scope: str | None, ctags_scope_kind: str | None) -> str:
    if ctags_scope_kind:
        mapped = _SCOPE_MAP.get(ctags_scope_kind.lower())
        if mapped:
            return mapped
    if ctags_scope:
        mapped = _SCOPE_MAP.get(ctags_scope.lower())
        if mapped:
            return mapped
    return "global"


def _confidence_for_tag(tag: dict, our_kind: str) -> tuple[str, str]:
    """Определить confidence и confidence_reason для тега ctags."""
    ctags_kind = tag.get("kind", "").lower()

    if ctags_kind in _IS_DECLARATION_KINDS:
        return "MEDIUM", "prototype/extern declaration, not a definition"

    if our_kind in ("function", "variable", "typedef", "struct", "union", "enum"):
        return "HIGH", "ctags full definition"

    if our_kind in ("enumerator", "field", "macro"):
        return "HIGH", "ctags definition"

    if our_kind == "label":
        return "MEDIUM", "ctags label (scope may be ambiguous)"

    return "MEDIUM", "unmapped ctags kind"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def extract_entities(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    logger=None,
) -> dict:
    """Извлечь сущности C-кода через ctags, записать в таблицу entities.

    Args:
        source_root: корень дерева исходников
        db_path:     путь к SQLite
        run_id:      ID прогона
        logger:      опциональный structlog-логгер

    Returns:
        {stage, status, count, errors, elapsed_sec, ctags_error}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    count = 0

    lg.info("extract_entities_start", source_root=str(source_root))

    tags, ctags_err = _run_ctags(source_root)
    if ctags_err:
        lg.warning("ctags_error", error=ctags_err)
        if not tags:
            elapsed = time.monotonic() - t0
            return {
                "stage": "extract_entities",
                "status": "error",
                "count": 0,
                "errors": [{"stage": "extract_entities", "error": ctags_err}],
                "elapsed_sec": round(elapsed, 2),
                "ctags_error": ctags_err,
            }

    lg.info("ctags_tags_received", total=len(tags))

    with get_db(db_path) as conn:
        # Построить индекс path→file_id
        file_rows = conn.execute(
            "SELECT file_id, path, absolute_path FROM files WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        # ctags возвращает пути относительно CWD (source_root)
        relpath_to_id: dict[str, int] = {r["path"]: r["file_id"] for r in file_rows}
        # также по абсолютному пути на случай если ctags вернёт абсолютный
        abspath_to_relpath: dict[str, str] = {
            str(Path(r["absolute_path"]).resolve()): r["path"] for r in file_rows
        }

        for tag in tags:
            tag_path: str = tag.get("path", "")

            # Нормализация пути тега → относительный путь в нашей БД
            rel_path: str | None = None
            if tag_path in relpath_to_id:
                rel_path = tag_path
            else:
                # ctags может вернуть абсолютный или другой вариант
                try:
                    abs_candidate = str(
                        (source_root / tag_path).resolve()
                        if not Path(tag_path).is_absolute()
                        else Path(tag_path).resolve()
                    )
                    rel_path = abspath_to_relpath.get(abs_candidate)
                except Exception:
                    pass

            if rel_path is None:
                errors.append({
                    "stage": "extract_entities",
                    "file": tag_path,
                    "error": f"file not in DB for run_id={run_id}",
                })
                continue

            file_id = relpath_to_id[rel_path]
            abs_file = Path(
                conn.execute(
                    "SELECT absolute_path FROM files WHERE file_id = ?", (file_id,)
                ).fetchone()["absolute_path"]
            )

            name: str = tag.get("name", "")
            ctags_kind: str = tag.get("kind", "")
            our_kind = _map_kind(ctags_kind)
            line_number: int = tag.get("line", 0)
            signature: str | None = tag.get("signature")
            ctags_scope: str | None = tag.get("scope")
            ctags_scope_kind: str | None = tag.get("scopeKind")
            scope = _map_scope(ctags_scope, ctags_scope_kind)

            is_declaration = 1 if ctags_kind.lower() in _IS_DECLARATION_KINDS else 0
            is_definition = 0 if is_declaration else 1

            confidence, confidence_reason = _confidence_for_tag(tag, our_kind)
            raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be = get_raw_context(
                abs_file, line_number
            )

            try:
                conn.execute(
                    """
                    INSERT INTO entities (
                        run_id, file_id, name, kind, scope,
                        line_start, signature,
                        is_declaration, is_definition,
                        detector, confidence, confidence_reason,
                        raw_context,
                        raw_context_line_start, raw_context_line_end,
                        raw_context_byte_start, raw_context_byte_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id, file_id, name, our_kind, scope,
                        line_number, signature,
                        is_declaration, is_definition,
                        "ctags", confidence, confidence_reason,
                        raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be,
                    ),
                )
                count += 1
            except Exception as exc:
                errors.append({
                    "stage": "extract_entities",
                    "file": rel_path,
                    "entity": name,
                    "error": str(exc),
                })
                lg.warning("entity_insert_error", name=name, file=rel_path, error=str(exc))

        conn.commit()

    elapsed = time.monotonic() - t0
    lg.info(
        "extract_entities_done",
        count=count,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "extract_entities",
        "status": "ok" if not errors else "partial",
        "count": count,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
        "ctags_error": ctags_err,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="extract-entities")
@click.option("--source-dir", "-s", required=True, type=click.Path(exists=True))
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--run-id", "run_id", type=int, default=None)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(source_dir: str, db_path: str, run_id: int | None, verbose: bool) -> None:
    """Извлечь сущности C-кода через ctags."""
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

    result = extract_entities(Path(source_dir), Path(db_path), run_id)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
