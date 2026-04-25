"""Стадия: извлечение сущностей и точек вызова C-кода.

Запускает universal-ctags с --output-format=json, парсит JSONL-вывод,
записывает сущности в таблицу entities.

Затем делает AST-проход через tree-sitter-c по каждому файлу и извлекает
точки вызова функций в таблицу call_sites, включая macro-wrapper chain
для function-like макросов.

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
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click
import structlog

from src.db.schema import create_run, get_db, init_db
from src.utils import get_raw_context, run_command, tool_available

try:
    from tree_sitter import Language, Parser
    import tree_sitter_c
except (ImportError, AttributeError, TypeError) as exc:  # pragma: no cover - depends on environment
    Language = None  # type: ignore[assignment]
    Parser = None  # type: ignore[assignment]
    tree_sitter_c = None  # type: ignore[assignment]
    _TREE_SITTER_IMPORT_ERROR: str | None = str(exc)
else:
    _TREE_SITTER_IMPORT_ERROR = None

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

_DEFINE_FUNC_RE = re.compile(
    r"^\s*#\s*define\s+(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^)]*)\)\s*(?P<value>.*)$"
)
_MACRO_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_MACRO_CALL_KEYWORDS: frozenset[str] = frozenset({
    "if", "while", "for", "switch", "sizeof", "return", "defined",
})

_EXTERN_VAR_DECL_RE = re.compile(
    r"^\s*extern\s+(?P<type>[^;()]+?)\s+(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*;\s*$"
)


@dataclass(slots=True)
class _MacroDefinition:
    name: str
    params: set[str]
    call_names: list[str]


def _extract_extern_variable_declarations_for_file(abs_file: Path) -> list[dict]:
    """Fallback для extern переменных, которые ctags мог пропустить.

    Возвращает список:
      [{name, line_number, signature}, ...]
    """
    try:
        lines = abs_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    records: list[dict] = []
    for lineno, line in enumerate(lines, start=1):
        if "extern" not in line:
            continue
        # Функции и function pointers оставляем ctags/AST-проходу.
        if "(" in line or ")" in line:
            continue
        match = _EXTERN_VAR_DECL_RE.match(line)
        if not match:
            continue

        var_name = match.group("name")
        signature = line.strip().rstrip(";")
        records.append({
            "name": var_name,
            "line_number": lineno,
            "signature": signature,
        })
    return records


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


def _iter_nodes(root, wanted_types: set[str] | None = None):
    stack = [root]
    while stack:
        node = stack.pop()
        if wanted_types is None or node.type in wanted_types:
            yield node
        children = getattr(node, "children", None) or []
        stack.extend(reversed(children))


def _node_text(source_bytes: bytes, node) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _rightmost_identifier_text(node, source_bytes: bytes) -> str | None:
    result: str | None = None
    for child in _iter_nodes(node, {"identifier", "field_identifier"}):
        result = _node_text(source_bytes, child)
    return result


def _extract_invoked_name(function_node, source_bytes: bytes) -> str | None:
    if function_node is None:
        return None
    if function_node.type == "identifier":
        return _node_text(source_bytes, function_node)
    if function_node.type == "field_expression":
        return _rightmost_identifier_text(function_node, source_bytes)
    return None


def _build_macro_definitions(root, source_bytes: bytes) -> dict[str, _MacroDefinition]:
    macros: dict[str, _MacroDefinition] = {}
    for node in _iter_nodes(root, {"preproc_function_def"}):
        match = _DEFINE_FUNC_RE.match(_node_text(source_bytes, node))
        if not match:
            continue
        name = match.group("name")
        params = {
            part.strip()
            for part in match.group("params").split(",")
            if part.strip()
        }
        body = match.group("value")
        call_names: list[str] = []
        for candidate in _MACRO_CALL_RE.findall(body):
            if candidate in params or candidate in _MACRO_CALL_KEYWORDS:
                continue
            if candidate not in call_names:
                call_names.append(candidate)
        macros[name] = _MacroDefinition(
            name=name,
            params=params,
            call_names=call_names,
        )
    return macros


def _resolve_macro_chain(
    invoked_name: str,
    macros: dict[str, _MacroDefinition],
) -> tuple[str, list[str]]:
    chain: list[str] = []
    current = invoked_name
    visited: set[str] = set()

    while current in macros and current not in visited:
        visited.add(current)
        chain.append(current)
        next_calls = [name for name in macros[current].call_names if name not in visited]
        if not next_calls:
            break
        current = next_calls[0]

    return current, chain


def _find_function_entity_by_line(
    function_rows: list[dict],
    line_number: int,
) -> dict | None:
    exact = next((row for row in function_rows if row["line_start"] == line_number), None)
    if exact is not None:
        return exact

    nearby = [
        row for row in function_rows
        if row["line_start"] is not None and abs(row["line_start"] - line_number) <= 2
    ]
    if len(nearby) == 1:
        return nearby[0]
    return None


def _resolve_function_entity(
    callee_name: str,
    file_id: int,
    function_rows_by_name: dict[str, list[dict]],
) -> dict | None:
    candidates = function_rows_by_name.get(callee_name, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    same_file = [row for row in candidates if row["file_id"] == file_id]
    if len(same_file) == 1:
        return same_file[0]

    global_candidates = [row for row in candidates if row.get("scope") != "static"]
    if len(global_candidates) == 1:
        return global_candidates[0]

    return None


def _extract_call_sites_for_file(
    abs_file: Path,
    run_id: int,
    file_id: int,
    function_rows: list[dict],
    function_rows_by_name: dict[str, list[dict]],
) -> tuple[list[dict], list[dict]]:
    if _TREE_SITTER_IMPORT_ERROR is not None or Parser is None or Language is None or tree_sitter_c is None:
        return [], [{
            "stage": "extract_entities",
            "file": str(abs_file),
            "error": f"tree-sitter unavailable: {_TREE_SITTER_IMPORT_ERROR}",
        }]

    try:
        source_bytes = abs_file.read_bytes()
    except OSError as exc:
        return [], [{
            "stage": "extract_entities",
            "file": str(abs_file),
            "error": str(exc),
        }]

    parser = Parser()
    parser.language = Language(tree_sitter_c.language())
    tree = parser.parse(source_bytes)
    root = tree.root_node

    macros = _build_macro_definitions(root, source_bytes)
    records: list[dict] = []
    errors: list[dict] = []

    for fn_node in _iter_nodes(root, {"function_definition"}):
        line_start = fn_node.start_point.row + 1
        caller_row = _find_function_entity_by_line(function_rows, line_start)
        if caller_row is None:
            continue

        body_node = fn_node.child_by_field_name("body")
        if body_node is None:
            continue

        for call_node in _iter_nodes(body_node, {"call_expression"}):
            function_node = call_node.child_by_field_name("function")
            invoked_name = _extract_invoked_name(function_node, source_bytes)
            if not invoked_name:
                continue

            callee_name = invoked_name
            macro_names: list[str] = []
            if invoked_name in macros:
                callee_name, macro_names = _resolve_macro_chain(invoked_name, macros)

            callee_row = _resolve_function_entity(callee_name, file_id, function_rows_by_name)

            line_number = call_node.start_point.row + 1
            col_start = call_node.start_point.column + 1
            col_end = call_node.end_point.column + 1
            raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be = get_raw_context(abs_file, line_number)

            confidence = "MEDIUM"
            confidence_reason = "tree-sitter call expression"
            if callee_row is not None and not macro_names:
                confidence = "HIGH"
                confidence_reason = "tree-sitter direct call resolved to function entity"
            elif callee_row is not None and macro_names:
                confidence = "HIGH"
                confidence_reason = "tree-sitter call resolved through macro wrapper chain"
            elif macro_names:
                confidence_reason = "tree-sitter macro-mediated call with unresolved terminal callee"
            elif function_node is not None and function_node.type == "field_expression":
                confidence_reason = "tree-sitter member or method-like call expression"

            records.append({
                "run_id": run_id,
                "file_id": file_id,
                "caller_entity_id": caller_row["entity_id"],
                "caller_name": caller_row["name"],
                "callee_entity_id": callee_row["entity_id"] if callee_row else None,
                "callee_name": callee_name,
                "invoked_name": invoked_name,
                "call_text": _node_text(source_bytes, call_node),
                "line_number": line_number,
                "col_start": col_start,
                "col_end": col_end,
                "byte_start": call_node.start_byte,
                "byte_end": call_node.end_byte,
                "macro_names": json.dumps(macro_names, ensure_ascii=False) if macro_names else None,
                "detector": "tree_sitter",
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "raw_context": raw_ctx,
                "raw_context_line_start": ctx_ls,
                "raw_context_line_end": ctx_le,
                "raw_context_byte_start": ctx_bs,
                "raw_context_byte_end": ctx_be,
            })

    return records, errors


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
        {stage, status, count, call_sites, errors, elapsed_sec, ctags_error}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    count = 0
    call_site_count = 0

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
                except OSError:
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
            except sqlite3.Error as exc:
                errors.append({
                    "stage": "extract_entities",
                    "file": rel_path,
                    "entity": name,
                    "error": str(exc),
                })
                lg.warning("entity_insert_error", name=name, file=rel_path, error=str(exc))

        # Fallback: добавить extern variable declarations, которые могли выпасть из ctags.
        for file_row in file_rows:
            file_id = file_row["file_id"]
            rel_path = file_row["path"]
            abs_file = Path(file_row["absolute_path"])
            decls = _extract_extern_variable_declarations_for_file(abs_file)
            for decl in decls:
                exists = conn.execute(
                    """
                    SELECT 1
                    FROM entities
                    WHERE run_id = ?
                      AND file_id = ?
                      AND name = ?
                      AND kind = 'variable'
                      AND line_start = ?
                    LIMIT 1
                    """,
                    (run_id, file_id, decl["name"], decl["line_number"]),
                ).fetchone()
                if exists:
                    continue

                raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be = get_raw_context(
                    abs_file, decl["line_number"]
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
                            run_id, file_id, decl["name"], "variable", "extern",
                            decl["line_number"], decl["signature"],
                            1, 0,
                            "regex", "MEDIUM", "extern variable declaration fallback",
                            raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be,
                        ),
                    )
                    count += 1
                except sqlite3.Error as exc:
                    errors.append({
                        "stage": "extract_entities",
                        "file": rel_path,
                        "entity": decl["name"],
                        "error": str(exc),
                    })
                    lg.warning("extern_decl_insert_error", name=decl["name"], file=rel_path, error=str(exc))

        function_rows = [
            dict(row) for row in conn.execute(
                """
                SELECT entity_id, file_id, name, line_start, scope
                FROM entities
                WHERE run_id = ? AND kind = 'function' AND is_definition = 1
                """,
                (run_id,),
            ).fetchall()
        ]
        function_rows_by_file: dict[int, list[dict]] = {}
        function_rows_by_name: dict[str, list[dict]] = {}
        for row in function_rows:
            function_rows_by_file.setdefault(row["file_id"], []).append(row)
            function_rows_by_name.setdefault(row["name"], []).append(row)

        for file_row in file_rows:
            file_id = file_row["file_id"]
            abs_file = Path(file_row["absolute_path"])
            call_sites, call_errors = _extract_call_sites_for_file(
                abs_file,
                run_id,
                file_id,
                function_rows_by_file.get(file_id, []),
                function_rows_by_name,
            )
            errors.extend(call_errors)

            for call_site in call_sites:
                try:
                    conn.execute(
                        """
                        INSERT INTO call_sites (
                            run_id, file_id,
                            caller_entity_id, caller_name,
                            callee_entity_id, callee_name,
                            invoked_name, call_text,
                            line_number, col_start, col_end,
                            byte_start, byte_end,
                            macro_names,
                            detector, confidence, confidence_reason,
                            raw_context,
                            raw_context_line_start, raw_context_line_end,
                            raw_context_byte_start, raw_context_byte_end
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            call_site["run_id"], call_site["file_id"],
                            call_site["caller_entity_id"], call_site["caller_name"],
                            call_site["callee_entity_id"], call_site["callee_name"],
                            call_site["invoked_name"], call_site["call_text"],
                            call_site["line_number"], call_site["col_start"], call_site["col_end"],
                            call_site["byte_start"], call_site["byte_end"],
                            call_site["macro_names"],
                            call_site["detector"], call_site["confidence"], call_site["confidence_reason"],
                            call_site["raw_context"],
                            call_site["raw_context_line_start"], call_site["raw_context_line_end"],
                            call_site["raw_context_byte_start"], call_site["raw_context_byte_end"],
                        ),
                    )
                    call_site_count += 1
                except sqlite3.Error as exc:
                    errors.append({
                        "stage": "extract_entities",
                        "file": file_row["path"],
                        "call": call_site["call_text"],
                        "error": str(exc),
                    })
                    lg.warning("call_site_insert_error", file=file_row["path"], error=str(exc))

        conn.commit()

    elapsed = time.monotonic() - t0
    lg.info(
        "extract_entities_done",
        count=count,
        call_sites=call_site_count,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "extract_entities",
        "status": "ok" if not errors else "partial",
        "count": count,
        "call_sites": call_site_count,
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
    main()  # pyright: ignore[reportCallIssue]
