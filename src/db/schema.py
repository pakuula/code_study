"""Схема базы данных SQLite для C code analyzer.

Все основные таблицы содержат поля трассировки:
  detector          — источник факта (tree_sitter/ctags/cscope/regex/manual_rule)
  confidence        — уровень уверенности (HIGH/MEDIUM/LOW)
  confidence_reason — причина оценки уверенности
  raw_context       — текст ±3 строки вокруг позиции
  raw_context_line_start/end, byte_start/end — точные диапазоны
  ambiguity_group_id — ссылка на группу неоднозначности (NULL = однозначно)

Спорные/конкурирующие факты не удаляются — сохраняются с пометкой.

CLI:
  ./.venv/bin/python -m src.db.schema --db <path>
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, cast

# ---------------------------------------------------------------------------
# Путь к корню пакета (для запуска как скрипта)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click  # noqa: E402 — после path-fix

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

DDL: list[str] = [
    # ------------------------------------------------------------------
    # Метаданные прогонов
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS analysis_runs (
        run_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        source_root       TEXT    NOT NULL,
        db_path           TEXT    NOT NULL,
        started_at        TEXT    NOT NULL,
        finished_at       TEXT,
        pipeline_version  TEXT    DEFAULT '1.0.0',
        stages_completed  TEXT,        -- JSON array of completed stage names
        total_files       INTEGER DEFAULT 0,
        total_entities    INTEGER DEFAULT 0,
        total_references  INTEGER DEFAULT 0,
        total_comments    INTEGER DEFAULT 0,
        total_includes    INTEGER DEFAULT 0,
        errors            TEXT           -- JSON array: [{stage, file, error}]
    )
    """,
    # ------------------------------------------------------------------
    # Файлы исходного кода
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS files (
        file_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id         INTEGER NOT NULL,
        path           TEXT    NOT NULL,   -- relative to source_root
        absolute_path  TEXT    NOT NULL,
        size_bytes     INTEGER,
        sha256         TEXT,
        is_header      INTEGER NOT NULL DEFAULT 0,
        language       TEXT    DEFAULT 'c',
        FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id),
        UNIQUE (run_id, path)
    )
    """,
    # ------------------------------------------------------------------
    # Группы неоднозначности (для конкурирующих интерпретаций)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS ambiguity_groups (
        group_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      INTEGER NOT NULL,
        description TEXT,
        created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
    )
    """,
    # ------------------------------------------------------------------
    # Сущности C-кода: объявления и определения
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS entities (
        entity_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id             INTEGER NOT NULL,
        file_id            INTEGER NOT NULL,
        name               TEXT    NOT NULL,
        kind               TEXT    NOT NULL,
            -- function / variable / typedef / struct / union /
            -- enum / enumerator / macro / label / field / prototype
        scope              TEXT,
            -- global / static / local / extern / parameter
        line_start         INTEGER,
        col_start          INTEGER,
        line_end           INTEGER,
        col_end            INTEGER,
        byte_start         INTEGER,
        byte_end           INTEGER,
        signature          TEXT,          -- прототип функции, тип переменной и т.п.
        is_declaration     INTEGER DEFAULT 0,
        is_definition      INTEGER DEFAULT 1,
        parent_entity_id   INTEGER,       -- для полей структур, вложенных типов
        -- трассировка -------------------------------------------------------
        detector           TEXT    NOT NULL,
        confidence         TEXT    NOT NULL DEFAULT 'MEDIUM',
        confidence_reason  TEXT,
        raw_context        TEXT,
        raw_context_line_start INTEGER,
        raw_context_line_end   INTEGER,
        raw_context_byte_start INTEGER,
        raw_context_byte_end   INTEGER,
        ambiguity_group_id INTEGER,
        -- -------------------------------------------------------------------
        FOREIGN KEY (run_id)             REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)            REFERENCES files(file_id),
        FOREIGN KEY (parent_entity_id)   REFERENCES entities(entity_id),
        FOREIGN KEY (ambiguity_group_id) REFERENCES ambiguity_groups(group_id)
    )
    """,
    # ------------------------------------------------------------------
    # #include-директивы
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS includes (
        include_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id            INTEGER NOT NULL,
        source_file_id    INTEGER NOT NULL,
        line_number       INTEGER NOT NULL,
        include_path      TEXT    NOT NULL,   -- литерал из #include
        include_type      TEXT    NOT NULL,   -- quoted / angled
        resolved_file_id  INTEGER,            -- NULL если не удалось разрешить
        is_resolved       INTEGER DEFAULT 0,
        -- трассировка -------------------------------------------------------
        detector          TEXT    NOT NULL DEFAULT 'regex',
        confidence        TEXT    NOT NULL DEFAULT 'HIGH',
        confidence_reason TEXT,
        raw_context       TEXT,
        raw_context_line_start INTEGER,
        raw_context_line_end   INTEGER,
        raw_context_byte_start INTEGER,
        raw_context_byte_end   INTEGER,
        ambiguity_group_id INTEGER,
        -- -------------------------------------------------------------------
        FOREIGN KEY (run_id)             REFERENCES analysis_runs(run_id),
        FOREIGN KEY (source_file_id)     REFERENCES files(file_id),
        FOREIGN KEY (resolved_file_id)   REFERENCES files(file_id),
        FOREIGN KEY (ambiguity_group_id) REFERENCES ambiguity_groups(group_id)
    )
    """,
    # ------------------------------------------------------------------
    # Все попытки резолва #include (все кандидаты, не только выбранный)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS include_resolution_attempts (
        attempt_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        include_id      INTEGER NOT NULL,
        candidate_path  TEXT    NOT NULL,
        search_dir      TEXT,
        resolved        INTEGER DEFAULT 0,
        FOREIGN KEY (include_id) REFERENCES includes(include_id)
    )
    """,
    # ------------------------------------------------------------------
    # Комментарии
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS comments (
        comment_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id             INTEGER NOT NULL,
        file_id            INTEGER NOT NULL,
        line_start         INTEGER NOT NULL,
        line_end           INTEGER NOT NULL,
        col_start          INTEGER,
        col_end            INTEGER,
        byte_start         INTEGER,
        byte_end           INTEGER,
        text               TEXT    NOT NULL,
        comment_type       TEXT    NOT NULL,  -- line_comment / block_comment
        -- трассировка -------------------------------------------------------
        detector           TEXT    NOT NULL DEFAULT 'regex',
        confidence         TEXT    NOT NULL DEFAULT 'HIGH',
        confidence_reason  TEXT,
        raw_context        TEXT,
        raw_context_line_start INTEGER,
        raw_context_line_end   INTEGER,
        raw_context_byte_start INTEGER,
        raw_context_byte_end   INTEGER,
        ambiguity_group_id INTEGER,
        -- -------------------------------------------------------------------
        FOREIGN KEY (run_id)             REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)            REFERENCES files(file_id),
        FOREIGN KEY (ambiguity_group_id) REFERENCES ambiguity_groups(group_id)
    )
    """,
    # ------------------------------------------------------------------
    # Привязка комментариев к сущностям
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS entity_comments (
        entity_id        INTEGER NOT NULL,
        comment_id       INTEGER NOT NULL,
        association_type TEXT    NOT NULL,  -- preceding / inline
        distance_lines   INTEGER,           -- строк между концом комментария и началом сущности
        PRIMARY KEY (entity_id, comment_id),
        FOREIGN KEY (entity_id)  REFERENCES entities(entity_id),
        FOREIGN KEY (comment_id) REFERENCES comments(comment_id)
    )
    """,
    # ------------------------------------------------------------------
    # Кандидаты на использования (reference_candidates)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS reference_candidates (
        ref_id             INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id             INTEGER NOT NULL,
        file_id            INTEGER NOT NULL,
        name               TEXT    NOT NULL,
        line_number        INTEGER NOT NULL,
        col_start          INTEGER,
        col_end            INTEGER,
        byte_start         INTEGER,
        byte_end           INTEGER,
        candidate_type     TEXT    NOT NULL,
            -- call_candidate / read_write_candidate /
            -- macro_expansion_candidate / type_reference_candidate
        access_kind        TEXT,
            -- read / write / call / type_ref / macro_exp  (NULL допустимо)
        resolved_entity_id INTEGER,   -- NULL если не удалось связать с сущностью
        scope_distance     INTEGER,   -- дистанция от объявления до использования в scope-уровнях
        candidate_rank     INTEGER,   -- порядок при нескольких кандидатах на одну позицию
        -- трассировка -------------------------------------------------------
        detector           TEXT    NOT NULL,
        confidence         TEXT    NOT NULL DEFAULT 'MEDIUM',
        confidence_reason  TEXT,
        raw_context        TEXT,
        raw_context_line_start INTEGER,
        raw_context_line_end   INTEGER,
        raw_context_col_start  INTEGER,
        raw_context_col_end    INTEGER,
        raw_context_byte_start INTEGER,
        raw_context_byte_end   INTEGER,
        ambiguity_group_id INTEGER,
        -- -------------------------------------------------------------------
        FOREIGN KEY (run_id)             REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)            REFERENCES files(file_id),
        FOREIGN KEY (resolved_entity_id) REFERENCES entities(entity_id),
        FOREIGN KEY (ambiguity_group_id) REFERENCES ambiguity_groups(group_id)
    )
    """,
    # ------------------------------------------------------------------
    # Точки вызова функций / call graph edges
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS call_sites (
        call_id             INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id              INTEGER NOT NULL,
        file_id             INTEGER NOT NULL,
        caller_entity_id    INTEGER,
        caller_name         TEXT,
        callee_entity_id    INTEGER,
        callee_name         TEXT    NOT NULL,
        invoked_name        TEXT    NOT NULL,
        call_text           TEXT,
        line_number         INTEGER NOT NULL,
        col_start           INTEGER,
        col_end             INTEGER,
        byte_start          INTEGER,
        byte_end            INTEGER,
        macro_names         TEXT,              -- JSON array of macro wrappers
        detector            TEXT    NOT NULL,
        confidence          TEXT    NOT NULL DEFAULT 'MEDIUM',
        confidence_reason   TEXT,
        raw_context         TEXT,
        raw_context_line_start INTEGER,
        raw_context_line_end   INTEGER,
        raw_context_byte_start INTEGER,
        raw_context_byte_end   INTEGER,
        ambiguity_group_id  INTEGER,
        FOREIGN KEY (run_id)             REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)            REFERENCES files(file_id),
        FOREIGN KEY (caller_entity_id)   REFERENCES entities(entity_id),
        FOREIGN KEY (callee_entity_id)   REFERENCES entities(entity_id),
        FOREIGN KEY (ambiguity_group_id) REFERENCES ambiguity_groups(group_id)
    )
    """,
    # ------------------------------------------------------------------
    # Условные регионы (#if / #ifdef / #else / #endif)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS conditional_regions (
        region_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id           INTEGER NOT NULL,
        file_id          INTEGER NOT NULL,
        directive        TEXT    NOT NULL,  -- if/ifdef/ifndef/elif/else/endif
        condition        TEXT,              -- выражение-условие
        line_start       INTEGER NOT NULL,
        line_end         INTEGER,           -- NULL если endif не найден
        depth            INTEGER DEFAULT 0,
        parent_region_id INTEGER,
        FOREIGN KEY (run_id)           REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)          REFERENCES files(file_id),
        FOREIGN KEY (parent_region_id) REFERENCES conditional_regions(region_id)
    )
    """,
    # ------------------------------------------------------------------
    # Препроцессорные символы (#define и т.п.)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS preprocessor_symbols (
        symbol_id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id                 INTEGER NOT NULL,
        file_id                INTEGER NOT NULL,
        name                   TEXT    NOT NULL,
        symbol_type            TEXT    NOT NULL,  -- define / undef / include_guard
        line_number            INTEGER NOT NULL,
        value                  TEXT,              -- тело подстановки для #define
        params                 TEXT,              -- JSON-массив для function-like макросов
        is_function_like       INTEGER DEFAULT 0,
        conditional_region_id  INTEGER,
        FOREIGN KEY (run_id)                REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)               REFERENCES files(file_id),
        FOREIGN KEY (conditional_region_id) REFERENCES conditional_regions(region_id)
    )
    """,
    # ------------------------------------------------------------------
    # Условия присутствия сущностей (какие #ifdef нужны для сущности)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS entity_presence_conditions (
        epc_id                INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id             INTEGER NOT NULL,
        conditional_region_id INTEGER NOT NULL,
        condition_text        TEXT,
        FOREIGN KEY (entity_id)             REFERENCES entities(entity_id),
        FOREIGN KEY (conditional_region_id) REFERENCES conditional_regions(region_id)
    )
    """,
    # ------------------------------------------------------------------
    # typedef alias graph: alias -> target type
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS type_aliases (
        alias_id               INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id                 INTEGER NOT NULL,
        file_id                INTEGER NOT NULL,
        alias_entity_id        INTEGER,
        alias_name             TEXT    NOT NULL,
        target_spelling        TEXT,
        target_base_name       TEXT,
        target_kind            TEXT,    -- typedef / struct / union / enum / builtin / unknown
        indirection_level      INTEGER DEFAULT 0,
        detector               TEXT    NOT NULL,
        confidence             TEXT    NOT NULL DEFAULT 'MEDIUM',
        confidence_reason      TEXT,
        raw_context            TEXT,
        raw_context_line_start INTEGER,
        raw_context_line_end   INTEGER,
        raw_context_byte_start INTEGER,
        raw_context_byte_end   INTEGER,
        ambiguity_group_id     INTEGER,
        FOREIGN KEY (run_id)             REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)            REFERENCES files(file_id),
        FOREIGN KEY (alias_entity_id)    REFERENCES entities(entity_id),
        FOREIGN KEY (ambiguity_group_id) REFERENCES ambiguity_groups(group_id)
    )
    """,
    # ------------------------------------------------------------------
    # typedef chain resolution to non-typedef type
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS type_resolutions (
        resolution_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id                 INTEGER NOT NULL,
        alias_id               INTEGER NOT NULL,
        alias_entity_id        INTEGER,
        alias_name             TEXT    NOT NULL,
        final_type_name        TEXT,
        final_type_kind        TEXT,    -- struct / union / enum / builtin / unknown
        total_indirection_level INTEGER DEFAULT 0,
        is_composite           INTEGER, -- 1 for struct/union/enum, 0 otherwise, NULL unknown
        resolution_path        TEXT,    -- JSON array of names
        is_cycle               INTEGER DEFAULT 0,
        is_ambiguous           INTEGER DEFAULT 0,
        detector               TEXT    NOT NULL,
        confidence             TEXT    NOT NULL DEFAULT 'MEDIUM',
        confidence_reason      TEXT,
        FOREIGN KEY (run_id)          REFERENCES analysis_runs(run_id),
        FOREIGN KEY (alias_id)        REFERENCES type_aliases(alias_id),
        FOREIGN KEY (alias_entity_id) REFERENCES entities(entity_id)
    )
    """,
    # ------------------------------------------------------------------
    # usage of types in signatures, global/static vars, fields, typedef targets
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS type_uses (
        type_use_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id                 INTEGER NOT NULL,
        file_id                INTEGER NOT NULL,
        line_number            INTEGER NOT NULL,
        col_start              INTEGER,
        col_end                INTEGER,
        type_name              TEXT    NOT NULL,
        owner_name             TEXT,
        enclosing_function     TEXT,
            -- NULL for global/field/typedef_target; func name for func_param/func_return/local_var
        use_context            TEXT    NOT NULL,
            -- func_param / func_return / global_var / static_var / field / typedef_target / local_var
        by_pointer             INTEGER DEFAULT 0,
        indirection_level      INTEGER DEFAULT 0,
        resolved_alias_id      INTEGER,
        resolved_alias_entity_id INTEGER,
        resolved_final_type_name TEXT,
        resolved_final_type_kind TEXT,
        resolved_is_composite  INTEGER,
        detector               TEXT    NOT NULL,
        confidence             TEXT    NOT NULL DEFAULT 'MEDIUM',
        confidence_reason      TEXT,
        raw_context            TEXT,
        raw_context_line_start INTEGER,
        raw_context_line_end   INTEGER,
        raw_context_byte_start INTEGER,
        raw_context_byte_end   INTEGER,
        ambiguity_group_id     INTEGER,
        FOREIGN KEY (run_id)                 REFERENCES analysis_runs(run_id),
        FOREIGN KEY (file_id)                REFERENCES files(file_id),
        FOREIGN KEY (resolved_alias_id)      REFERENCES type_aliases(alias_id),
        FOREIGN KEY (resolved_alias_entity_id) REFERENCES entities(entity_id),
        FOREIGN KEY (ambiguity_group_id)     REFERENCES ambiguity_groups(group_id)
    )
    """,
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_files_run         ON files(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_files_path        ON files(run_id, path)",
    "CREATE INDEX IF NOT EXISTS idx_entities_name     ON entities(name)",
    "CREATE INDEX IF NOT EXISTS idx_entities_file     ON entities(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_entities_kind     ON entities(kind, scope)",
    "CREATE INDEX IF NOT EXISTS idx_entities_run      ON entities(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_entities_conf     ON entities(confidence)",
    "CREATE INDEX IF NOT EXISTS idx_includes_src      ON includes(source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_includes_resolved ON includes(resolved_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_includes_run      ON includes(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_comments_file     ON comments(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_comments_line     ON comments(file_id, line_start)",
    "CREATE INDEX IF NOT EXISTS idx_refs_name         ON reference_candidates(name)",
    "CREATE INDEX IF NOT EXISTS idx_refs_file         ON reference_candidates(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_refs_entity       ON reference_candidates(resolved_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_refs_run          ON reference_candidates(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_refs_conf         ON reference_candidates(confidence)",
    "CREATE INDEX IF NOT EXISTS idx_calls_run         ON call_sites(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_calls_file        ON call_sites(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_calls_caller      ON call_sites(caller_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_calls_callee      ON call_sites(callee_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_cond_file         ON conditional_regions(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_cond_run          ON conditional_regions(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_pp_name           ON preprocessor_symbols(name)",
    "CREATE INDEX IF NOT EXISTS idx_pp_file           ON preprocessor_symbols(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_epc_entity        ON entity_presence_conditions(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_talias_run        ON type_aliases(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_talias_name       ON type_aliases(alias_name)",
    "CREATE INDEX IF NOT EXISTS idx_talias_target     ON type_aliases(target_base_name)",
    "CREATE INDEX IF NOT EXISTS idx_tres_run          ON type_resolutions(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_tres_alias        ON type_resolutions(alias_name)",
    "CREATE INDEX IF NOT EXISTS idx_tuses_run         ON type_uses(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_tuses_encfn       ON type_uses(run_id, enclosing_function)",
    "CREATE INDEX IF NOT EXISTS idx_tuses_name        ON type_uses(type_name)",
    "CREATE INDEX IF NOT EXISTS idx_tuses_ctx         ON type_uses(use_context)",
    "CREATE INDEX IF NOT EXISTS idx_ambig_run         ON ambiguity_groups(run_id)",
]

VIEWS: list[str] = [
    """
    CREATE VIEW IF NOT EXISTS v_call_edges AS
    SELECT
        cs.call_id,
        cs.run_id,
        cs.file_id,
        f.path AS file_path,
        cs.caller_entity_id,
        COALESCE(caller.name, cs.caller_name) AS caller_name,
        caller.signature AS caller_signature,
        cs.callee_entity_id,
        COALESCE(callee.name, cs.callee_name) AS callee_name,
        callee.signature AS callee_signature,
        cs.invoked_name,
        cs.call_text,
        cs.line_number,
        cs.col_start,
        cs.col_end,
        cs.byte_start,
        cs.byte_end,
        cs.macro_names,
        cs.detector,
        cs.confidence,
        cs.confidence_reason,
        cs.raw_context,
        cs.raw_context_line_start,
        cs.raw_context_line_end,
        cs.raw_context_byte_start,
        cs.raw_context_byte_end,
        cs.ambiguity_group_id
    FROM call_sites cs
    JOIN files f ON f.file_id = cs.file_id
    LEFT JOIN entities caller ON caller.entity_id = cs.caller_entity_id
    LEFT JOIN entities callee ON callee.entity_id = cs.callee_entity_id
    """,
    """
    CREATE VIEW IF NOT EXISTS v_call_out AS
    SELECT
        call_id,
        run_id,
        caller_entity_id,
        caller_name,
        caller_signature,
        callee_entity_id,
        callee_name,
        callee_signature,
        invoked_name,
        file_id,
        file_path,
        line_number,
        col_start,
        col_end,
        call_text,
        macro_names,
        detector,
        confidence,
        confidence_reason,
        raw_context,
        ambiguity_group_id
    FROM v_call_edges
    """,
    """
    CREATE VIEW IF NOT EXISTS v_call_in AS
    SELECT
        call_id,
        run_id,
        callee_entity_id,
        callee_name,
        callee_signature,
        caller_entity_id,
        caller_name,
        caller_signature,
        invoked_name,
        file_id,
        file_path,
        line_number,
        col_start,
        col_end,
        call_text,
        macro_names,
        detector,
        confidence,
        confidence_reason,
        raw_context,
        ambiguity_group_id
    FROM v_call_edges
    """,
    """
    CREATE VIEW IF NOT EXISTS v_variable_entities AS
    SELECT
        e.entity_id,
        e.run_id,
        e.file_id,
        f.path AS file_path,
        e.name AS variable_name,
        e.scope,
        e.signature,
        e.line_start,
        e.is_declaration,
        e.is_definition,
        e.detector,
        e.confidence,
        e.confidence_reason,
        e.raw_context,
        e.ambiguity_group_id
    FROM entities e
    JOIN files f ON f.file_id = e.file_id
    WHERE e.kind = 'variable'
    """,
    """
    CREATE VIEW IF NOT EXISTS v_variable_uses AS
    SELECT
        rc.ref_id,
        rc.run_id,
        rc.file_id,
        f.path AS file_path,
        rc.line_number,
        rc.col_start,
        rc.col_end,
        rc.name AS variable_name,
        rc.candidate_type,
        rc.access_kind,
        rc.resolved_entity_id,
        ve.scope AS resolved_scope,
        ve.file_id AS resolved_file_id,
        vf.path AS resolved_file_path,
        (
            SELECT ef.name
            FROM entities ef
            WHERE ef.run_id = rc.run_id
              AND ef.file_id = rc.file_id
              AND ef.kind = 'function'
              AND ef.is_definition = 1
              AND ef.line_start <= rc.line_number
            ORDER BY ef.line_start DESC
            LIMIT 1
        ) AS enclosing_function,
        rc.detector,
        rc.confidence,
        rc.confidence_reason,
        rc.raw_context,
        rc.ambiguity_group_id
    FROM reference_candidates rc
    JOIN files f ON f.file_id = rc.file_id
    LEFT JOIN entities ve ON ve.entity_id = rc.resolved_entity_id
    LEFT JOIN files vf ON vf.file_id = ve.file_id
    WHERE rc.candidate_type = 'read_write_candidate'
      AND (
          ve.kind = 'variable'
          OR rc.resolved_entity_id IS NULL
      )
      AND NOT EXISTS (
          SELECT 1
          FROM entities ed
          WHERE ed.run_id = rc.run_id
            AND ed.file_id = rc.file_id
            AND ed.name = rc.name
            AND ed.kind = 'variable'
            AND ed.line_start = rc.line_number
      )
    """,
    """
    CREATE VIEW IF NOT EXISTS v_type_aliases AS
    SELECT
        ta.alias_id,
        ta.run_id,
        ta.file_id,
        f.path AS file_path,
        ta.alias_entity_id,
        ta.alias_name,
        ta.target_spelling,
        ta.target_base_name,
        ta.target_kind,
        ta.indirection_level,
        ta.detector,
        ta.confidence,
        ta.confidence_reason,
        ta.raw_context,
        ta.ambiguity_group_id
    FROM type_aliases ta
    JOIN files f ON f.file_id = ta.file_id
    """,
    """
    CREATE VIEW IF NOT EXISTS v_type_resolutions AS
    SELECT
        tr.resolution_id,
        tr.run_id,
        tr.alias_id,
        tr.alias_entity_id,
        tr.alias_name,
        tr.final_type_name,
        tr.final_type_kind,
        tr.total_indirection_level,
        tr.is_composite,
        tr.resolution_path,
        tr.is_cycle,
        tr.is_ambiguous,
        tr.detector,
        tr.confidence,
        tr.confidence_reason,
        ta.file_id,
        f.path AS file_path
    FROM type_resolutions tr
    JOIN type_aliases ta ON ta.alias_id = tr.alias_id
    JOIN files f ON f.file_id = ta.file_id
    """,
    """
    CREATE VIEW IF NOT EXISTS v_type_uses AS
    SELECT
        tu.type_use_id,
        tu.run_id,
        tu.file_id,
        f.path AS file_path,
        tu.line_number,
        tu.col_start,
        tu.col_end,
        tu.type_name,
        tu.owner_name,
        tu.enclosing_function,
        tu.use_context,
        tu.by_pointer,
        tu.indirection_level,
        tu.resolved_alias_id,
        tu.resolved_alias_entity_id,
        tu.resolved_final_type_name,
        tu.resolved_final_type_kind,
        tu.resolved_is_composite,
        tu.detector,
        tu.confidence,
        tu.confidence_reason,
        tu.raw_context,
        tu.ambiguity_group_id
    FROM type_uses tu
    JOIN files f ON f.file_id = tu.file_id
    """,
]


# ---------------------------------------------------------------------------
# Хелперы подключения
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Создать или открыть БД, применить DDL и индексы. Вернуть соединение."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    for stmt in DDL:
        conn.execute(stmt)
    for stmt in INDEXES:
        conn.execute(stmt)
    for stmt in VIEWS:
        conn.execute(stmt)
    conn.commit()
    return conn


@contextmanager
def get_db(db_path: str | Path) -> Generator[sqlite3.Connection, None, None]:
    """Контекстный менеджер: открыть БД, commit при выходе, rollback при ошибке."""
    conn = init_db(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_run(
    conn: sqlite3.Connection,
    source_root: str | Path,
    db_path: str | Path,
) -> int:
    """Создать запись analysis_run, вернуть run_id."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO analysis_runs (source_root, db_path, started_at) VALUES (?, ?, ?)",
        (str(source_root), str(db_path), now),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    stages_completed: list[str],
    errors: list[dict],
) -> None:
    """Обновить запись analysis_run после завершения пайплайна."""
    import json

    def _count(table: str) -> int:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row[0] if row else 0

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE analysis_runs SET
            finished_at      = ?,
            stages_completed = ?,
            total_files      = ?,
            total_entities   = ?,
            total_references = ?,
            total_comments   = ?,
            total_includes   = ?,
            errors           = ?
        WHERE run_id = ?
        """,
        (
            now,
            json.dumps(stages_completed),
            _count("files"),
            _count("entities"),
            _count("reference_candidates"),
            _count("comments"),
            _count("includes"),
            json.dumps(errors),
            run_id,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="init-db")
@click.option(
    "--db", "db_path", required=True, type=click.Path(),
    help="Путь к файлу БД SQLite",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(db_path: str, verbose: bool) -> None:
    """Инициализировать схему базы данных (CREATE TABLE IF NOT EXISTS)."""
    import os
    conn = init_db(db_path)
    if verbose:
        click.echo(f"БД: {os.path.abspath(db_path)}")
        click.echo(f"Таблиц проверено: {len(DDL)}")
        click.echo(f"Индексов проверено: {len(INDEXES)}")
        click.echo(f"View проверено: {len(VIEWS)}")
    conn.close()
    click.echo(f"OK: {db_path}")


if __name__ == "__main__":
    cast(Any, main)()
