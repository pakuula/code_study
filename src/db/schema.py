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
from typing import Generator

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
    "CREATE INDEX IF NOT EXISTS idx_cond_file         ON conditional_regions(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_cond_run          ON conditional_regions(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_pp_name           ON preprocessor_symbols(name)",
    "CREATE INDEX IF NOT EXISTS idx_pp_file           ON preprocessor_symbols(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_epc_entity        ON entity_presence_conditions(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_ambig_run         ON ambiguity_groups(run_id)",
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
    conn.close()
    click.echo(f"OK: {db_path}")


if __name__ == "__main__":
    main()
