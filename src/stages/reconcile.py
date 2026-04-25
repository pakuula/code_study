"""Стадия: сверка (reconcile) результатов от разных детекторов.

Принципы:
  - Ничего не удаляется. Только confidence повышается/понижается.
  - При совпадении нескольких детекторов — confidence растёт (взвешенно).
  - При конфликте — записи помечаются через ambiguity_group_id.
  - Веса детекторов: tree_sitter > ctags > cscope > regex > manual_rule.

Алгоритм для entities:
  Группировка по (file_id, name, line_start).
  Если несколько записей в группе → создать ambiguity_group, проставить всем.
  Если tree_sitter + ctags в группе → лучшей записи поставить HIGH.
  Если только cscope + regex → не выше MEDIUM.

Алгоритм для reference_candidates:
  Группировка по (file_id, name, line_number).
  Для каждой группы проставить candidate_rank (1 = best).
  Если cscope-запись совпадает по позиции с regex → boost MEDIUM→HIGH.
  Если tree_sitter + ctags → HIGH.

API:
    from src.stages.reconcile import reconcile
    result = reconcile(source_root, db_path, run_id)

CLI:
    ./.venv/bin/python -m src.stages.reconcile \\
        --db <path> --run-id <run_id> [-v]
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

from src.db.schema import get_db, init_db

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Веса детекторов (чем выше — тем надёжнее)
# ---------------------------------------------------------------------------
DETECTOR_WEIGHT: dict[str, int] = {
    "tree_sitter":  5,
    "ctags":        4,
    "cscope":       3,
    "regex":        1,
    "manual_rule":  2,
}

# Пороги суммы весов → confidence
def _weight_to_confidence(total_weight: int, max_weight: int) -> str:
    """Взвешенное правило:
      - tree_sitter+ctags в группе → сумма ≥ 9 → HIGH
      - cscope+ctags → сумма ≥ 7 → HIGH
      - cscope+regex → сумма ≤ 4 → MEDIUM (не выше)
      - только regex → LOW
    """
    if total_weight >= 7:
        return "HIGH"
    if total_weight >= 3:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_ambiguity_group(
    conn,
    run_id: int,
    description: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO ambiguity_groups (run_id, description) VALUES (?, ?)",
        (run_id, description),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def reconcile(
    source_root: Path,
    db_path: Path,
    run_id: int,
    *,
    logger=None,
) -> dict:
    """Сверить результаты детекторов, обновить confidence и ambiguity_group_id.

    Args:
        source_root: корень дерева (используется только для логов)
        db_path:     путь к SQLite
        run_id:      ID прогона
        logger:      опциональный structlog-логгер

    Returns:
        {stage, status, entities_updated, refs_updated, ambiguity_groups_created, errors, elapsed_sec}
    """
    lg = logger or log
    t0 = time.monotonic()
    errors: list[dict] = []
    entities_updated = 0
    refs_updated = 0
    ambig_created = 0

    with get_db(db_path) as conn:
        # ==================================================================
        # 1. Reconcile entities
        # ==================================================================
        lg.info("reconcile_entities_start")

        entities = conn.execute(
            """
            SELECT entity_id, file_id, name, line_start, detector, confidence
            FROM entities
            WHERE run_id = ?
            ORDER BY file_id, name, line_start, detector
            """,
            (run_id,),
        ).fetchall()

        # Группировать по (file_id, name, line_start)
        entity_groups: dict[tuple, list] = {}
        for e in entities:
            key = (e["file_id"], e["name"], e["line_start"])
            entity_groups.setdefault(key, []).append(dict(e))

        for key, group in entity_groups.items():
            if len(group) == 1:
                continue  # нет конфликта, не трогаем

            # Несколько записей для одной позиции → ambiguity_group
            detectors = {g["detector"] for g in group}
            desc = (
                f"entity '{key[1]}' at file={key[0]} line={key[2]}: "
                f"detectors={sorted(detectors)}"
            )
            ag_id = _create_ambiguity_group(conn, run_id, desc)
            ambig_created += 1

            # Вычислить суммарный вес
            total_weight = sum(DETECTOR_WEIGHT.get(g["detector"], 1) for g in group)
            new_confidence = _weight_to_confidence(total_weight, max(DETECTOR_WEIGHT.values()))
            reason = (
                f"reconcile: {len(group)} detectors agree "
                f"(weight={total_weight}) → {new_confidence}"
            )

            for g in group:
                try:
                    conn.execute(
                        """
                        UPDATE entities
                        SET confidence = ?,
                            confidence_reason = ?,
                            ambiguity_group_id = ?
                        WHERE entity_id = ?
                        """,
                        (new_confidence, reason, ag_id, g["entity_id"]),
                    )
                    entities_updated += 1
                except Exception as exc:
                    errors.append({"stage": "reconcile", "error": str(exc)})

        # ==================================================================
        # 2. Reconcile reference_candidates
        # ==================================================================
        lg.info("reconcile_refs_start")

        refs = conn.execute(
            """
            SELECT ref_id, file_id, name, line_number, detector, confidence, candidate_type
            FROM reference_candidates
            WHERE run_id = ?
            ORDER BY file_id, name, line_number, detector
            """,
            (run_id,),
        ).fetchall()

        ref_groups: dict[tuple, list] = {}
        for r in refs:
            key = (r["file_id"], r["name"], r["line_number"])
            ref_groups.setdefault(key, []).append(dict(r))

        for key, group in ref_groups.items():
            # Проставить candidate_rank (1 = самый надёжный детектор)
            sorted_group = sorted(
                group,
                key=lambda g: -DETECTOR_WEIGHT.get(g["detector"], 1),
            )
            for rank, g in enumerate(sorted_group, start=1):
                try:
                    conn.execute(
                        "UPDATE reference_candidates SET candidate_rank = ? WHERE ref_id = ?",
                        (rank, g["ref_id"]),
                    )
                    refs_updated += 1
                except Exception as exc:
                    errors.append({"stage": "reconcile", "error": str(exc)})

            if len(group) == 1:
                continue

            # Несколько детекторов → boost/ambiguity
            detectors = {g["detector"] for g in group}
            total_weight = sum(DETECTOR_WEIGHT.get(g["detector"], 1) for g in group)
            new_confidence = _weight_to_confidence(total_weight, max(DETECTOR_WEIGHT.values()))

            # Если детекторы конфликтуют по candidate_type → ambiguity_group
            ctypes = {g["candidate_type"] for g in group}
            ag_id: int | None = None
            if len(ctypes) > 1:
                desc = (
                    f"ref '{key[1]}' at file={key[0]} line={key[2]}: "
                    f"conflicting types={sorted(ctypes)}"
                )
                ag_id = _create_ambiguity_group(conn, run_id, desc)
                ambig_created += 1
                reason = (
                    f"reconcile: candidate_type conflict {sorted(ctypes)}, "
                    f"weight={total_weight} → {new_confidence}"
                )
            else:
                reason = (
                    f"reconcile: {len(group)} detectors agree "
                    f"(weight={total_weight}) → {new_confidence}"
                )

            for g in group:
                try:
                    conn.execute(
                        """
                        UPDATE reference_candidates
                        SET confidence = ?,
                            confidence_reason = ?,
                            ambiguity_group_id = ?
                        WHERE ref_id = ?
                        """,
                        (new_confidence, reason, ag_id, g["ref_id"]),
                    )
                except Exception as exc:
                    errors.append({"stage": "reconcile", "error": str(exc)})

        conn.commit()

    elapsed = time.monotonic() - t0
    lg.info(
        "reconcile_done",
        entities_updated=entities_updated,
        refs_updated=refs_updated,
        ambiguity_groups=ambig_created,
        errors=len(errors),
        elapsed_sec=round(elapsed, 2),
    )
    return {
        "stage": "reconcile",
        "status": "ok" if not errors else "partial",
        "entities_updated": entities_updated,
        "refs_updated": refs_updated,
        "ambiguity_groups_created": ambig_created,
        "errors": errors,
        "elapsed_sec": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="reconcile")
@click.option("--source-dir", "-s", default=".", type=click.Path(), help="Корень (для логов)")
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--run-id", "run_id", type=int, required=True)
@click.option("-v", "--verbose", is_flag=True, default=False)
def main(source_dir: str, db_path: str, run_id: int, verbose: bool) -> None:
    """Сверить результаты детекторов, обновить confidence."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if verbose
            else structlog.processors.JSONRenderer(),
        ]
    )
    result = reconcile(Path(source_dir), Path(db_path), run_id)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
