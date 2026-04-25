"""Стадия: извлечение typedef-цепочек и использования типов (без локальных переменных).

Извлекает через tree-sitter-c:
  - typedef alias -> target (таблица type_aliases)
  - разрешение typedef-цепочек до конечного (non-typedef) типа (type_resolutions)
  - использования типов в контекстах:
      * func_param
      * func_return
      * global_var
      * static_var
      * field
      * typedef_target
    (таблица type_uses)

Ограничение текущей версии:
  - локальные декларации (внутри функций) намеренно не извлекаются.
"""
from __future__ import annotations

import json
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
from src.utils import C_EXTENSIONS, get_raw_context

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


@dataclass(slots=True)
class _AliasRow:
    file_id: int
    alias_entity_id: int | None
    alias_name: str
    target_spelling: str
    target_base_name: str | None
    target_kind: str
    indirection_level: int
    line_number: int
    raw_context: str
    raw_context_line_start: int
    raw_context_line_end: int
    raw_context_byte_start: int
    raw_context_byte_end: int


@dataclass(slots=True)
class _TypeUseRow:
    file_id: int
    line_number: int
    col_start: int | None
    col_end: int | None
    type_name: str
    owner_name: str | None
    use_context: str
    by_pointer: int
    indirection_level: int
    confidence: str
    confidence_reason: str
    raw_context: str
    raw_context_line_start: int
    raw_context_line_end: int
    raw_context_byte_start: int
    raw_context_byte_end: int


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


def _find_first_identifier_text(node, source_bytes: bytes) -> str | None:
    for child in _iter_nodes(node, {"identifier", "field_identifier", "type_identifier"}):
        return _node_text(source_bytes, child)
    return None


def _unwrap_declarator(node, source_bytes: bytes) -> tuple[str | None, int, bool]:
    """Вернуть (name, pointer_depth, is_function_declarator)."""
    if node is None:
        return None, 0, False

    t = node.type
    if t in {"identifier", "field_identifier", "type_identifier"}:
        return _node_text(source_bytes, node), 0, False

    if t == "init_declarator":
        inner = node.child_by_field_name("declarator")
        return _unwrap_declarator(inner, source_bytes)

    if t == "pointer_declarator":
        inner = node.child_by_field_name("declarator")
        name, ptr, is_func = _unwrap_declarator(inner, source_bytes)
        return name, ptr + 1, is_func

    if t in {"parenthesized_declarator", "array_declarator"}:
        inner = node.child_by_field_name("declarator")
        return _unwrap_declarator(inner, source_bytes)

    if t == "function_declarator":
        inner = node.child_by_field_name("declarator")
        name, ptr, _ = _unwrap_declarator(inner, source_bytes)
        return name, ptr, True

    # Fallback: пытаемся найти декларатор рекурсивно.
    for child in node.children:
        if child.type in {
            "init_declarator",
            "pointer_declarator",
            "parenthesized_declarator",
            "array_declarator",
            "function_declarator",
            "identifier",
            "field_identifier",
            "type_identifier",
        }:
            return _unwrap_declarator(child, source_bytes)

    return None, 0, False


def _collect_declarator_nodes(node) -> list:
    """Собрать declarator-ноды у declaration/field_declaration."""
    result = []
    type_node = node.child_by_field_name("type")
    for child in node.children:
        if type_node is not None and child.id == type_node.id:
            continue
        if child.type in {
            ",",
            ";",
            "storage_class_specifier",
            "type_qualifier",
            "attribute_specifier",
            "ms_declspec_modifier",
        }:
            continue
        if child.type in {
            "init_declarator",
            "pointer_declarator",
            "array_declarator",
            "function_declarator",
            "parenthesized_declarator",
            "identifier",
            "field_identifier",
            "type_identifier",
        }:
            result.append(child)
    return result


def _type_info(type_node, source_bytes: bytes) -> tuple[str, str | None, str]:
    """Вернуть (spelling, base_name, kind)."""
    spelling = _node_text(source_bytes, type_node).strip()

    if type_node.type == "type_identifier":
        return spelling, spelling, "typedef"

    if type_node.type in {"primitive_type", "sized_type_specifier", "type_qualifier"}:
        return spelling, spelling, "builtin"

    if type_node.type in {"struct_specifier", "union_specifier", "enum_specifier"}:
        if type_node.type == "struct_specifier":
            kind = "struct"
            prefix = "struct"
        elif type_node.type == "union_specifier":
            kind = "union"
            prefix = "union"
        else:
            kind = "enum"
            prefix = "enum"

        tag = _find_first_identifier_text(type_node, source_bytes)
        base = f"{prefix} {tag}" if tag else spelling
        return spelling, base, kind

    # fallback
    ident = _find_first_identifier_text(type_node, source_bytes)
    if ident:
        return spelling, ident, "unknown"
    return spelling, spelling, "unknown"


def _create_ambiguity_group(conn, run_id: int, description: str) -> int:
    cur = conn.execute(
        "INSERT INTO ambiguity_groups (run_id, description) VALUES (?, ?)",
        (run_id, description),
    )
    return cur.lastrowid


def _pick_alias_candidate(candidates: list[dict], preferred_file_id: int) -> tuple[dict | None, bool]:
    if not candidates:
        return None, False
    same_file = [c for c in candidates if c["file_id"] == preferred_file_id]
    if len(same_file) == 1:
        return same_file[0], False
    if len(same_file) > 1:
        return None, True
    if len(candidates) == 1:
        return candidates[0], False
    return None, True


def _is_top_level_declaration(node) -> bool:
    parent = getattr(node, "parent", None)
    return parent is not None and parent.type == "translation_unit"


def _get_containing_struct_name(fld_node, source_bytes: bytes) -> str | None:
    """Вернуть имя struct/union, которому принадлежит field_declaration.

    Родительская цепочка:
      field_declaration -> field_declaration_list -> struct_specifier / union_specifier
    Из struct_specifier берём field 'name' (type_identifier с тегом).
    Если тег анонимный — возвращаем None.
    """
    parent = getattr(fld_node, "parent", None)   # field_declaration_list
    if parent is None:
        return None
    grandparent = getattr(parent, "parent", None)  # struct_specifier / union_specifier
    if grandparent is None:
        return None
    if grandparent.type not in {"struct_specifier", "union_specifier"}:
        return None
    name_node = grandparent.child_by_field_name("name")
    if name_node is None:
        return None
    return _node_text(source_bytes, name_node).strip() or None


def _extract_file_rows(
    file_id: int,
    abs_path: Path,
    parser,
    typedef_entity_map: dict[tuple[int, str], list[dict]],
) -> tuple[list[_AliasRow], list[_TypeUseRow], list[dict]]:
    alias_rows: list[_AliasRow] = []
    use_rows: list[_TypeUseRow] = []
    errors: list[dict] = []

    try:
        source_bytes = abs_path.read_bytes()
    except OSError as exc:
        return [], [], [{"stage": "extract_types", "file": str(abs_path), "error": str(exc)}]

    root = parser.parse(source_bytes).root_node

    # ------------------------------------------------------------------
    # typedef: alias -> target
    # ------------------------------------------------------------------
    for td in _iter_nodes(root, {"type_definition"}):
        type_node = td.child_by_field_name("type")
        declarator = td.child_by_field_name("declarator")
        if type_node is None or declarator is None:
            continue

        alias_name, ptr_depth, is_func = _unwrap_declarator(declarator, source_bytes)
        if not alias_name or is_func:
            continue

        target_spelling, target_base_name, target_kind = _type_info(type_node, source_bytes)
        line_number = td.start_point[0] + 1
        raw, ls, le, bs, be = get_raw_context(abs_path, line_number)

        alias_entity_id: int | None = None
        candidates = typedef_entity_map.get((file_id, alias_name), [])
        if candidates:
            exact = [c for c in candidates if c["line_start"] == line_number]
            chosen = exact[0] if exact else candidates[0]
            alias_entity_id = chosen["entity_id"]

        alias_rows.append(
            _AliasRow(
                file_id=file_id,
                alias_entity_id=alias_entity_id,
                alias_name=alias_name,
                target_spelling=target_spelling,
                target_base_name=target_base_name,
                target_kind=target_kind,
                indirection_level=ptr_depth,
                line_number=line_number,
                raw_context=raw,
                raw_context_line_start=ls,
                raw_context_line_end=le,
                raw_context_byte_start=bs,
                raw_context_byte_end=be,
            )
        )

        # typedef target usage (если target содержит имя типа)
        if target_base_name:
            use_rows.append(
                _TypeUseRow(
                    file_id=file_id,
                    line_number=line_number,
                    col_start=type_node.start_point[1] + 1,
                    col_end=type_node.end_point[1] + 1,
                    type_name=target_base_name,
                    owner_name=alias_name,
                    use_context="typedef_target",
                    by_pointer=1 if ptr_depth > 0 else 0,
                    indirection_level=ptr_depth,
                    confidence="HIGH",
                    confidence_reason="tree_sitter typedef target",
                    raw_context=raw,
                    raw_context_line_start=ls,
                    raw_context_line_end=le,
                    raw_context_byte_start=bs,
                    raw_context_byte_end=be,
                )
            )

    # ------------------------------------------------------------------
    # function return + params (definitions + prototypes)
    # ------------------------------------------------------------------
    function_owner_nodes = []
    function_owner_nodes.extend(_iter_nodes(root, {"function_definition"}))

    # prototypes: top-level declaration with function declarator
    for decl in _iter_nodes(root, {"declaration"}):
        if not _is_top_level_declaration(decl):
            continue
        has_function = False
        for dnode in _collect_declarator_nodes(decl):
            _, _, is_func = _unwrap_declarator(dnode, source_bytes)
            if is_func:
                has_function = True
                break
        if has_function:
            function_owner_nodes.append(decl)

    for fn in function_owner_nodes:
        type_node = fn.child_by_field_name("type")
        declarator = fn.child_by_field_name("declarator")
        if type_node is None or declarator is None:
            continue

        func_name, ret_ptr_depth, _ = _unwrap_declarator(declarator, source_bytes)
        _, ret_base_name, ret_kind = _type_info(type_node, source_bytes)
        if ret_kind != "builtin" and ret_base_name:
            line_number = fn.start_point[0] + 1
            raw, ls, le, bs, be = get_raw_context(abs_path, line_number)
            use_rows.append(
                _TypeUseRow(
                    file_id=file_id,
                    line_number=line_number,
                    col_start=type_node.start_point[1] + 1,
                    col_end=type_node.end_point[1] + 1,
                    type_name=ret_base_name,
                    owner_name=func_name,
                    use_context="func_return",
                    by_pointer=1 if ret_ptr_depth > 0 else 0,
                    indirection_level=ret_ptr_depth,
                    confidence="HIGH",
                    confidence_reason="tree_sitter function return type",
                    raw_context=raw,
                    raw_context_line_start=ls,
                    raw_context_line_end=le,
                    raw_context_byte_start=bs,
                    raw_context_byte_end=be,
                )
            )

        for p in _iter_nodes(declarator, {"parameter_declaration"}):
            p_type = p.child_by_field_name("type")
            p_decl = p.child_by_field_name("declarator")
            if p_type is None:
                continue
            _, p_base_name, p_kind = _type_info(p_type, source_bytes)
            if p_kind == "builtin" or not p_base_name:
                continue

            _, p_ptr_depth, _ = _unwrap_declarator(p_decl, source_bytes)
            line_number = p.start_point[0] + 1
            raw, ls, le, bs, be = get_raw_context(abs_path, line_number)
            use_rows.append(
                _TypeUseRow(
                    file_id=file_id,
                    line_number=line_number,
                    col_start=p_type.start_point[1] + 1,
                    col_end=p_type.end_point[1] + 1,
                    type_name=p_base_name,
                    owner_name=func_name,
                    use_context="func_param",
                    by_pointer=1 if p_ptr_depth > 0 else 0,
                    indirection_level=p_ptr_depth,
                    confidence="HIGH",
                    confidence_reason="tree_sitter function parameter type",
                    raw_context=raw,
                    raw_context_line_start=ls,
                    raw_context_line_end=le,
                    raw_context_byte_start=bs,
                    raw_context_byte_end=be,
                )
            )

    # ------------------------------------------------------------------
    # top-level declarations: global/static vars only (без локальных)
    # ------------------------------------------------------------------
    for decl in _iter_nodes(root, {"declaration"}):
        if not _is_top_level_declaration(decl):
            continue
        type_node = decl.child_by_field_name("type")
        if type_node is None:
            continue

        _, base_name, kind = _type_info(type_node, source_bytes)
        if kind == "builtin" or not base_name:
            continue

        is_static = any(ch.type == "storage_class_specifier" and _node_text(source_bytes, ch).strip() == "static" for ch in decl.children)

        for dnode in _collect_declarator_nodes(decl):
            owner_name, ptr_depth, is_func = _unwrap_declarator(dnode, source_bytes)
            if is_func:
                continue
            line_number = dnode.start_point[0] + 1
            raw, ls, le, bs, be = get_raw_context(abs_path, line_number)
            use_rows.append(
                _TypeUseRow(
                    file_id=file_id,
                    line_number=line_number,
                    col_start=type_node.start_point[1] + 1,
                    col_end=type_node.end_point[1] + 1,
                    type_name=base_name,
                    owner_name=owner_name,
                    use_context="static_var" if is_static else "global_var",
                    by_pointer=1 if ptr_depth > 0 else 0,
                    indirection_level=ptr_depth,
                    confidence="HIGH",
                    confidence_reason="tree_sitter top-level variable type",
                    raw_context=raw,
                    raw_context_line_start=ls,
                    raw_context_line_end=le,
                    raw_context_byte_start=bs,
                    raw_context_byte_end=be,
                )
            )

    # ------------------------------------------------------------------
    # struct/union fields
    # owner_name = имя родительской структуры/union (не имя поля)
    # ------------------------------------------------------------------
    for fld in _iter_nodes(root, {"field_declaration"}):
        type_node = fld.child_by_field_name("type")
        if type_node is None:
            continue

        _, base_name, kind = _type_info(type_node, source_bytes)
        if kind == "builtin" or not base_name:
            continue

        struct_name = _get_containing_struct_name(fld, source_bytes)
        line_number = fld.start_point[0] + 1
        raw, ls, le, bs, be = get_raw_context(abs_path, line_number)

        # Определяем pointer depth через первый declarator
        declarators = _collect_declarator_nodes(fld)
        if declarators:
            _, ptr_depth, _ = _unwrap_declarator(declarators[0], source_bytes)
        else:
            ptr_depth = 0
        by_ptr = 1 if ptr_depth > 0 else 0

        use_rows.append(
            _TypeUseRow(
                file_id=file_id,
                line_number=line_number,
                col_start=type_node.start_point[1] + 1,
                col_end=type_node.end_point[1] + 1,
                type_name=base_name,
                owner_name=struct_name,
                use_context="field",
                by_pointer=by_ptr,
                indirection_level=ptr_depth,
                confidence="HIGH",
                confidence_reason="tree_sitter field type",
                raw_context=raw,
                raw_context_line_start=ls,
                raw_context_line_end=le,
                raw_context_byte_start=bs,
                raw_context_byte_end=be,
            )
        )

    return alias_rows, use_rows, errors


def extract_types(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    logger=None,
) -> dict:
    """Извлечь typedef alias-chain и uses типов (без локальных переменных)."""
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []

    if _TREE_SITTER_IMPORT_ERROR is not None or Parser is None or Language is None or tree_sitter_c is None:
        return {
            "stage": "extract_types",
            "status": "partial",
            "type_aliases": 0,
            "type_resolutions": 0,
            "type_uses": 0,
            "errors": [{
                "stage": "extract_types",
                "error": f"tree-sitter-c unavailable: {_TREE_SITTER_IMPORT_ERROR}",
            }],
            "elapsed_sec": round(time.monotonic() - t0, 2),
        }

    parser = Parser()
    parser.language = Language(tree_sitter_c.language())

    lg.info("extract_types_start", source_root=str(source_root), run_id=run_id)

    aliases_inserted = 0
    resolutions_inserted = 0
    uses_inserted = 0

    with get_db(db_path) as conn:
        conn.execute("DELETE FROM type_uses WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM type_resolutions WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM type_aliases WHERE run_id = ?", (run_id,))

        typedef_entity_rows = conn.execute(
            """
            SELECT entity_id, file_id, name, line_start
            FROM entities
            WHERE run_id = ? AND kind = 'typedef'
            """,
            (run_id,),
        ).fetchall()
        typedef_entity_map: dict[tuple[int, str], list[dict]] = {}
        for row in typedef_entity_rows:
            key = (row["file_id"], row["name"])
            typedef_entity_map.setdefault(key, []).append(dict(row))

        file_rows = conn.execute(
            """
            SELECT file_id, path, absolute_path
            FROM files
            WHERE run_id = ?
            ORDER BY file_id
            """,
            (run_id,),
        ).fetchall()

        all_alias_rows: list[_AliasRow] = []
        all_use_rows: list[_TypeUseRow] = []

        for f in file_rows:
            abs_path = Path(f["absolute_path"])
            if abs_path.suffix.lower() not in C_EXTENSIONS:
                continue

            a_rows, u_rows, errs = _extract_file_rows(
                file_id=f["file_id"],
                abs_path=abs_path,
                parser=parser,
                typedef_entity_map=typedef_entity_map,
            )
            all_alias_rows.extend(a_rows)
            all_use_rows.extend(u_rows)
            if errs:
                errors.extend(errs)

        # ------------------------------------------------------------------
        # Insert aliases
        # ------------------------------------------------------------------
        for row in all_alias_rows:
            try:
                conn.execute(
                    """
                    INSERT INTO type_aliases (
                        run_id, file_id, alias_entity_id,
                        alias_name, target_spelling, target_base_name, target_kind,
                        indirection_level,
                        detector, confidence, confidence_reason,
                        raw_context, raw_context_line_start, raw_context_line_end,
                        raw_context_byte_start, raw_context_byte_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        row.file_id,
                        row.alias_entity_id,
                        row.alias_name,
                        row.target_spelling,
                        row.target_base_name,
                        row.target_kind,
                        row.indirection_level,
                        "tree_sitter",
                        "HIGH",
                        "tree_sitter typedef extraction",
                        row.raw_context,
                        row.raw_context_line_start,
                        row.raw_context_line_end,
                        row.raw_context_byte_start,
                        row.raw_context_byte_end,
                    ),
                )
                aliases_inserted += 1
            except sqlite3.Error as exc:
                errors.append({"stage": "extract_types", "error": str(exc), "alias": row.alias_name})

        # ------------------------------------------------------------------
        # Insert type uses
        # ------------------------------------------------------------------
        for row in all_use_rows:
            try:
                conn.execute(
                    """
                    INSERT INTO type_uses (
                        run_id, file_id,
                        line_number, col_start, col_end,
                        type_name, owner_name, use_context,
                        by_pointer, indirection_level,
                        detector, confidence, confidence_reason,
                        raw_context, raw_context_line_start, raw_context_line_end,
                        raw_context_byte_start, raw_context_byte_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        row.file_id,
                        row.line_number,
                        row.col_start,
                        row.col_end,
                        row.type_name,
                        row.owner_name,
                        row.use_context,
                        row.by_pointer,
                        row.indirection_level,
                        "tree_sitter",
                        row.confidence,
                        row.confidence_reason,
                        row.raw_context,
                        row.raw_context_line_start,
                        row.raw_context_line_end,
                        row.raw_context_byte_start,
                        row.raw_context_byte_end,
                    ),
                )
                uses_inserted += 1
            except sqlite3.Error as exc:
                errors.append({"stage": "extract_types", "error": str(exc), "type_name": row.type_name})

        # ------------------------------------------------------------------
        # Resolve typedef chains
        # ------------------------------------------------------------------
        alias_rows = conn.execute(
            """
            SELECT
                alias_id, file_id, alias_entity_id, alias_name,
                target_base_name, target_kind, indirection_level
            FROM type_aliases
            WHERE run_id = ?
            ORDER BY alias_id
            """,
            (run_id,),
        ).fetchall()

        by_alias_name: dict[str, list[dict]] = {}
        alias_by_id: dict[int, dict] = {}
        for row in alias_rows:
            rowd = dict(row)
            by_alias_name.setdefault(rowd["alias_name"], []).append(rowd)
            alias_by_id[rowd["alias_id"]] = rowd

        for row in alias_rows:
            alias_id = row["alias_id"]
            alias_name = row["alias_name"]
            file_id = row["file_id"]
            alias_entity_id = row["alias_entity_id"]
            current_name = row["target_base_name"]
            current_kind = row["target_kind"]
            total_ptr = int(row["indirection_level"] or 0)

            path = [alias_name]
            seen = {alias_name}
            is_cycle = 0
            is_ambiguous = 0
            confidence = "HIGH"
            reason = "typedef chain resolved"

            if not current_name:
                confidence = "MEDIUM"
                reason = "typedef target base name is empty"
            else:
                path.append(current_name)

            steps = 0
            while current_name and current_kind == "typedef" and steps < 64:
                steps += 1
                candidates = by_alias_name.get(current_name, [])
                chosen, ambiguous = _pick_alias_candidate(candidates, file_id)
                if ambiguous:
                    is_ambiguous = 1
                    confidence = "MEDIUM"
                    reason = f"typedef target '{current_name}' has ambiguous candidates"
                    break
                if chosen is None:
                    confidence = "MEDIUM"
                    reason = f"typedef target '{current_name}' unresolved in current run"
                    break

                next_name = chosen["target_base_name"]
                next_kind = chosen["target_kind"]
                total_ptr += int(chosen["indirection_level"] or 0)

                if next_name and next_name in seen:
                    is_cycle = 1
                    confidence = "LOW"
                    reason = f"typedef cycle detected via '{next_name}'"
                    current_name = next_name
                    current_kind = next_kind
                    path.append(next_name)
                    break

                if next_name:
                    seen.add(next_name)
                    path.append(next_name)
                current_name = next_name
                current_kind = next_kind

            if steps >= 64 and confidence == "HIGH":
                confidence = "MEDIUM"
                reason = "typedef chain depth limit reached"

            final_name = current_name
            final_kind = current_kind if current_kind != "typedef" else "unknown"
            is_composite = 1 if final_kind in {"struct", "union", "enum"} else 0

            try:
                conn.execute(
                    """
                    INSERT INTO type_resolutions (
                        run_id, alias_id, alias_entity_id, alias_name,
                        final_type_name, final_type_kind,
                        total_indirection_level, is_composite,
                        resolution_path, is_cycle, is_ambiguous,
                        detector, confidence, confidence_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        alias_id,
                        alias_entity_id,
                        alias_name,
                        final_name,
                        final_kind,
                        total_ptr,
                        is_composite,
                        json.dumps(path, ensure_ascii=False),
                        is_cycle,
                        is_ambiguous,
                        "manual_rule",
                        confidence,
                        reason,
                    ),
                )
                resolutions_inserted += 1
            except sqlite3.Error as exc:
                errors.append({"stage": "extract_types", "error": str(exc), "alias": alias_name})

        # ------------------------------------------------------------------
        # Resolve type uses against typedef aliases
        # ------------------------------------------------------------------
        resolution_by_alias_id = {
            row["alias_id"]: dict(row)
            for row in conn.execute(
                """
                SELECT alias_id, final_type_name, final_type_kind, is_composite
                FROM type_resolutions
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchall()
        }

        use_rows = conn.execute(
            """
            SELECT type_use_id, file_id, type_name
            FROM type_uses
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()

        for u in use_rows:
            type_use_id = u["type_use_id"]
            type_name = u["type_name"]
            file_id = u["file_id"]

            candidates = by_alias_name.get(type_name, [])
            chosen, ambiguous = _pick_alias_candidate(candidates, file_id)

            if ambiguous:
                ag_id = _create_ambiguity_group(
                    conn,
                    run_id,
                    f"type_use '{type_name}' at file={file_id}: ambiguous typedef candidates",
                )
                conn.execute(
                    """
                    UPDATE type_uses
                    SET confidence = ?,
                        confidence_reason = ?,
                        ambiguity_group_id = ?
                    WHERE type_use_id = ?
                    """,
                    (
                        "MEDIUM",
                        "typedef resolution ambiguous",
                        ag_id,
                        type_use_id,
                    ),
                )
                continue

            if chosen is None:
                continue

            alias_id = chosen["alias_id"]
            res = resolution_by_alias_id.get(alias_id)

            conn.execute(
                """
                UPDATE type_uses
                SET resolved_alias_id = ?,
                    resolved_alias_entity_id = ?,
                    resolved_final_type_name = ?,
                    resolved_final_type_kind = ?,
                    resolved_is_composite = ?
                WHERE type_use_id = ?
                """,
                (
                    alias_id,
                    chosen.get("alias_entity_id"),
                    res.get("final_type_name") if res else None,
                    res.get("final_type_kind") if res else None,
                    res.get("is_composite") if res else None,
                    type_use_id,
                ),
            )

        conn.commit()

    elapsed = time.monotonic() - t0
    status = "ok" if not errors else "partial"
    lg.info(
        "extract_types_done",
        run_id=run_id,
        status=status,
        aliases=aliases_inserted,
        resolutions=resolutions_inserted,
        uses=uses_inserted,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "extract_types",
        "status": status,
        "type_aliases": aliases_inserted,
        "type_resolutions": resolutions_inserted,
        "type_uses": uses_inserted,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
    }


@click.command(name="extract_types")
@click.option("--source-dir", "source_dir", default=".", type=click.Path())
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--run-id", "run_id", type=int, required=False)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(source_dir: str, db_path: str, run_id: int | None, verbose: bool) -> None:
    """CLI-обёртка стадии extract_types."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if verbose
            else structlog.processors.JSONRenderer(),
        ]
    )

    src = Path(source_dir).resolve()
    db = Path(db_path).resolve()

    conn = init_db(db)
    if run_id is None:
        run_id = create_run(conn, src, db)
    conn.close()

    result = extract_types(src, db, run_id)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main.main(standalone_mode=True)
