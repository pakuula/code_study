"""Стадия: извлечение комментариев и привязка к сущностям.

Ищет // и /* */ комментарии в каждом файле с точными позициями.
После вставки в таблицу comments — привязывает к сущностям:
  - preceding: комментарий заканчивается не позже чем за 2 строки до сущности
  - inline:    комментарий начинается на той же строке, что и сущность

Детектор: 'regex', confidence: 'HIGH' (комментарии определяются однозначно).

API:
    from src.stages.extract_comments import extract_comments
    result = extract_comments(source_root, db_path, run_id)

CLI:
    ./.venv/bin/python -m src.stages.extract_comments \\
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

# Регексп для поиска комментариев.
# Порядок важен: блочный /* */ — сначала, иначе // может захватить начало блока.
# re.DOTALL позволяет /* */ охватывать несколько строк.
_COMMENT_RE = re.compile(
    r"(?P<block>/\*.*?\*/)|(?P<line>//[^\n]*)",
    re.DOTALL,
)

# Регексп для строковых литералов и символьных литералов (чтобы их исключить)
_STRING_RE = re.compile(
    r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'',
    re.DOTALL,
)


def _mask_strings(content: str) -> str:
    """Заменить строковые литералы пробелами, чтобы не ловить // внутри строк."""
    result = list(content)
    for m in _STRING_RE.finditer(content):
        for i in range(m.start(), m.end()):
            result[i] = " "
    return "".join(result)


def _offset_to_line_col(content: str, offset: int) -> tuple[int, int]:
    """Перевести байтовый офсет в (line_number, col) — оба 1-based."""
    before = content[:offset]
    line = before.count("\n") + 1
    col = offset - before.rfind("\n")
    return line, col


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def extract_comments(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    preceding_gap: int = 2,
    logger=None,
) -> dict:
    """Извлечь комментарии и привязать к сущностям.

    Args:
        source_root:    корень дерева исходников
        db_path:        путь к SQLite
        run_id:         ID прогона
        preceding_gap:  макс. строк между концом комментария и началом сущности
        logger:         опциональный structlog-логгер

    Returns:
        {stage, status, count, linked, errors, elapsed_sec}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    count = 0
    linked = 0

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
                raw_content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append({"stage": "extract_comments", "file": rel_path, "error": str(exc)})
                continue

            masked = _mask_strings(raw_content)

            for m in _COMMENT_RE.finditer(masked):
                is_block = m.group("block") is not None
                comment_type = "block_comment" if is_block else "line_comment"

                byte_start = m.start()
                byte_end = m.end()
                # Текст берём из оригинала (не замаскированного)
                text = raw_content[byte_start:byte_end]

                line_start, col_start = _offset_to_line_col(raw_content, byte_start)
                line_end, col_end = _offset_to_line_col(raw_content, max(byte_end - 1, byte_start))

                raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be = get_raw_context(
                    abs_path, line_start
                )

                try:
                    cur = conn.execute(
                        """
                        INSERT INTO comments (
                            run_id, file_id,
                            line_start, line_end, col_start, col_end,
                            byte_start, byte_end,
                            text, comment_type,
                            detector, confidence,
                            raw_context,
                            raw_context_line_start, raw_context_line_end,
                            raw_context_byte_start, raw_context_byte_end
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id, file_id,
                            line_start, line_end, col_start, col_end,
                            byte_start, byte_end,
                            text, comment_type,
                            "regex", "HIGH",
                            raw_ctx, ctx_ls, ctx_le, ctx_bs, ctx_be,
                        ),
                    )
                    count += 1
                    lg.debug(
                        "comment_inserted",
                        file=rel_path,
                        line=line_start,
                        type=comment_type,
                        comment_id=cur.lastrowid,
                    )
                except Exception as exc:
                    errors.append({
                        "stage": "extract_comments",
                        "file": rel_path,
                        "error": str(exc),
                    })

        conn.commit()

        # ------------------------------------------------------------------
        # Привязка комментариев к сущностям
        # ------------------------------------------------------------------
        entities = conn.execute(
            "SELECT entity_id, file_id, line_start FROM entities WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        for ent in entities:
            ent_id: int = ent["entity_id"]
            ent_file: int = ent["file_id"]
            ent_line: int = ent["line_start"] or 0

            # preceding: комментарий в том же файле, чей line_end ≤ ent_line
            # и line_end >= ent_line - preceding_gap - 1
            comments_in_file = conn.execute(
                """
                SELECT comment_id, line_start, line_end
                FROM comments
                WHERE run_id = ? AND file_id = ?
                  AND line_end <= ? AND line_end >= ?
                """,
                (
                    run_id, ent_file,
                    ent_line - 1,
                    ent_line - preceding_gap - 1,
                ),
            ).fetchall()

            for c in comments_in_file:
                distance = ent_line - c["line_end"] - 1
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO entity_comments
                            (entity_id, comment_id, association_type, distance_lines)
                        VALUES (?, ?, 'preceding', ?)
                        """,
                        (ent_id, c["comment_id"], max(0, distance)),
                    )
                    linked += 1
                except Exception:
                    pass

            # inline: комментарий начинается на той же строке, что сущность
            inline_comments = conn.execute(
                """
                SELECT comment_id FROM comments
                WHERE run_id = ? AND file_id = ? AND line_start = ?
                """,
                (run_id, ent_file, ent_line),
            ).fetchall()

            for c in inline_comments:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO entity_comments
                            (entity_id, comment_id, association_type, distance_lines)
                        VALUES (?, ?, 'inline', 0)
                        """,
                        (ent_id, c["comment_id"]),
                    )
                    linked += 1
                except Exception:
                    pass

        conn.commit()

    elapsed = time.monotonic() - t0
    lg.info(
        "extract_comments_done",
        count=count,
        linked=linked,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "extract_comments",
        "status": "ok" if not errors else "partial",
        "count": count,
        "linked": linked,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="extract-comments")
@click.option("--source-dir", "-s", required=True, type=click.Path(exists=True))
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--run-id", "run_id", type=int, default=None)
@click.option(
    "--preceding-gap", type=int, default=2,
    help="Максимальное число строк между концом комментария и началом сущности",
)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(
    source_dir: str,
    db_path: str,
    run_id: int | None,
    preceding_gap: int,
    verbose: bool,
) -> None:
    """Извлечь комментарии и привязать к сущностям."""
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

    result = extract_comments(
        Path(source_dir), Path(db_path), run_id,
        preceding_gap=preceding_gap,
    )
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
