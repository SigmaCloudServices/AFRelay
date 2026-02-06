import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from service.caea_resilience.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_cycle(cuit: int, periodo: int, orden: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT OR IGNORE INTO caea_cycle (cuit, periodo, orden, status, created_at, updated_at)
            VALUES (?, ?, ?, 'requested', ?, ?)
            """,
            (cuit, periodo, orden, now, now),
        )
        row = conn.execute(
            "SELECT * FROM caea_cycle WHERE cuit=? AND periodo=? AND orden=?",
            (cuit, periodo, orden),
        ).fetchone()
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_cycle_by_id(cycle_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM caea_cycle WHERE id=?", (cycle_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_cycle(cuit: int, periodo: int, orden: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM caea_cycle WHERE cuit=? AND periodo=? AND orden=?",
            (cuit, periodo, orden),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_active_cycle(cuit: int, periodo: int, orden: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT *
              FROM caea_cycle
             WHERE cuit=? AND periodo=? AND orden=?
               AND status='active'
               AND caea_code IS NOT NULL
             LIMIT 1
            """,
            (cuit, periodo, orden),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_cycle_from_afip(cycle_id: int, afip_result: dict[str, Any], status: str = "active") -> None:
    conn = get_connection()
    try:
        now = _now_iso()
        caea = ((afip_result or {}).get("ResultGet") or {}).get("CAEA")
        final_status = status if caea else "requested"
        last_error = None if caea else "missing_caea_code"
        conn.execute(
            """
            UPDATE caea_cycle
               SET caea_code=?, status=?, updated_at=?, last_error=?
             WHERE id=?
            """,
            (caea, final_status, now, last_error, cycle_id),
        )
    finally:
        conn.close()


def set_cycle_error(cycle_id: int, error: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE caea_cycle SET status='error', last_error=?, updated_at=? WHERE id=?",
            (error, _now_iso(), cycle_id),
        )
    finally:
        conn.close()


def set_cycle_status(cycle_id: int, status: str, error: str | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE caea_cycle SET status=?, last_error=?, updated_at=? WHERE id=?",
            (status, error, _now_iso(), cycle_id),
        )
    finally:
        conn.close()


def normalize_cycle_statuses() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE caea_cycle
               SET status='requested',
                   last_error='missing_caea_code',
                   updated_at=?
             WHERE status='active'
               AND (caea_code IS NULL OR TRIM(caea_code) = '')
            """,
            (_now_iso(),),
        )
    finally:
        conn.close()


def reserve_next_invoice_number(cuit: int, pto_vta: int, cbte_tipo: int) -> int:
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT MAX(cbte_nro) AS max_nro
              FROM caea_invoice
             WHERE cuit=? AND pto_vta=? AND cbte_tipo=?
            """,
            (cuit, pto_vta, cbte_tipo),
        ).fetchone()
        next_nro = int(row["max_nro"] or 0) + 1
        conn.commit()
        return next_nro
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_local_invoice(
    cycle_id: int,
    cuit: int,
    pto_vta: int,
    cbte_tipo: int,
    cbte_nro: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO caea_invoice
                (cycle_id, cuit, pto_vta, cbte_tipo, cbte_nro, payload_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'issued_local', ?, ?)
            """,
            (cycle_id, cuit, pto_vta, cbte_tipo, cbte_nro, json.dumps(payload), now, now),
        )
        row = conn.execute("SELECT * FROM caea_invoice WHERE id = last_insert_rowid()").fetchone()
        return dict(row)
    finally:
        conn.close()


def mark_invoice_informed(invoice_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE caea_invoice SET status='informed', updated_at=?, last_error=NULL WHERE id=?",
            (_now_iso(), invoice_id),
        )
    finally:
        conn.close()


def mark_invoice_error(invoice_id: int, error: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE caea_invoice SET status='error', updated_at=?, last_error=? WHERE id=?",
            (_now_iso(), error, invoice_id),
        )
    finally:
        conn.close()


def add_outbox_job(job_type: str, idempotency_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO afip_outbox
                (job_type, idempotency_key, payload_json, status, attempts, next_retry_at, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
            """,
            (job_type, idempotency_key, json.dumps(payload), now, now, now),
        )
    except sqlite3.IntegrityError:
        pass

    try:
        row = conn.execute(
            "SELECT * FROM afip_outbox WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if row and row["status"] == "failed":
            now = _now_iso()
            conn.execute(
                """
                UPDATE afip_outbox
                   SET status='pending', attempts=0, next_retry_at=?, updated_at=?, last_error=NULL
                 WHERE id=?
                """,
                (now, now, row["id"]),
            )
            row = conn.execute(
                "SELECT * FROM afip_outbox WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
        return dict(row)
    finally:
        conn.close()


def fetch_due_outbox_jobs(limit: int = 20) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT *
              FROM afip_outbox
             WHERE status IN ('pending', 'retrying')
               AND next_retry_at <= ?
             ORDER BY id ASC
             LIMIT ?
            """,
            (_now_iso(), limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_outbox_processing(job_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE afip_outbox SET status='processing', updated_at=? WHERE id=?",
            (_now_iso(), job_id),
        )
    finally:
        conn.close()


def mark_outbox_done(job_id: int, response: dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE afip_outbox
               SET status='done', updated_at=?, last_error=NULL, last_response_json=?
             WHERE id=?
            """,
            (_now_iso(), json.dumps(response), job_id),
        )
    finally:
        conn.close()


def mark_outbox_retry(job_id: int, attempts: int, next_retry_at: str, error: str) -> None:
    conn = get_connection()
    try:
        status = "failed" if attempts >= 10 else "retrying"
        conn.execute(
            """
            UPDATE afip_outbox
               SET status=?, attempts=?, next_retry_at=?, last_error=?, updated_at=?
             WHERE id=?
            """,
            (status, attempts, next_retry_at, error, _now_iso(), job_id),
        )
    finally:
        conn.close()


def list_outbox(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM afip_outbox WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM afip_outbox ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_caea_assignments(limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                c.id AS cycle_id,
                c.cuit AS cuit,
                c.periodo AS periodo,
                c.orden AS orden,
                c.caea_code AS caea_code,
                i.pto_vta AS pto_vta,
                i.cbte_tipo AS cbte_tipo,
                COUNT(*) AS invoices_count,
                MIN(i.cbte_nro) AS cbte_from,
                MAX(i.cbte_nro) AS cbte_to,
                SUM(CASE WHEN i.status='informed' THEN 1 ELSE 0 END) AS informed_count,
                SUM(CASE WHEN i.status='issued_local' THEN 1 ELSE 0 END) AS pending_inform_count,
                SUM(CASE WHEN i.status='error' THEN 1 ELSE 0 END) AS error_count
            FROM caea_invoice i
            JOIN caea_cycle c ON c.id = i.cycle_id
            GROUP BY c.id, c.cuit, c.periodo, c.orden, c.caea_code, i.pto_vta, i.cbte_tipo
            ORDER BY c.periodo DESC, c.orden DESC, i.pto_vta ASC, i.cbte_tipo ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
