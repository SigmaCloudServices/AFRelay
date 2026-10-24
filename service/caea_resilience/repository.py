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
        result_get = (afip_result or {}).get("ResultGet") or {}
        caea = result_get.get("CAEA")
        final_status = status if caea else "requested"
        last_error = None if caea else "missing_caea_code"
        conn.execute(
            """
            UPDATE caea_cycle
               SET caea_code=?, status=?, updated_at=?, last_error=?,
                   fch_vig_desde=?, fch_vig_hasta=?, fch_tope_inf=?
             WHERE id=?
            """,
            (
                caea, final_status, now, last_error,
                result_get.get("FchVigDesde"), result_get.get("FchVigHasta"), result_get.get("FchTopeInf"),
                cycle_id,
            ),
        )
    finally:
        conn.close()


def find_cycle_for_date(cuit: int, cbte_fch: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM caea_cycle
             WHERE cuit=? AND status='active' AND caea_code IS NOT NULL
               AND fch_vig_desde <= ? AND fch_vig_hasta >= ?
             ORDER BY periodo DESC, orden DESC LIMIT 1
            """,
            (cuit, cbte_fch, cbte_fch),
        ).fetchone()
        return dict(row) if row else None
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


def has_local_invoices(cuit: int, pto_vta: int, cbte_tipo: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM caea_invoice WHERE cuit=? AND pto_vta=? AND cbte_tipo=? LIMIT 1",
            (cuit, pto_vta, cbte_tipo),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def issue_local_invoice(
    cycle_id: int,
    cuit: int,
    pto_vta: int,
    cbte_tipo: int,
    payload: dict[str, Any],
    seed_last_nro: int | None,
) -> dict[str, Any]:
    """Reserve the next number and insert the invoice in one IMMEDIATE transaction.

    seed_last_nro is ARCA's last authorized number for this PV/type; it is only used
    when there are no local invoices yet.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT MAX(cbte_nro) AS max_nro FROM caea_invoice WHERE cuit=? AND pto_vta=? AND cbte_tipo=?",
            (cuit, pto_vta, cbte_tipo),
        ).fetchone()
        last = row["max_nro"] if row["max_nro"] is not None else int(seed_last_nro or 0)
        cbte_nro = int(last) + 1
        det = payload["FeDetReq"]["FECAEADetRequest"][0]
        det["CbteDesde"] = cbte_nro
        det["CbteHasta"] = cbte_nro
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO caea_invoice
                (cycle_id, cuit, pto_vta, cbte_tipo, cbte_nro, payload_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'issued_local', ?, ?)
            """,
            (cycle_id, cuit, pto_vta, cbte_tipo, cbte_nro, json.dumps(payload), now, now),
        )
        inserted = conn.execute("SELECT * FROM caea_invoice WHERE id = last_insert_rowid()").fetchone()
        conn.commit()
        return dict(inserted)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_invoice_informed(invoice_id: int, response: dict[str, Any] | None = None, message: str = "") -> None:
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            "UPDATE caea_invoice SET status='informed', informed_at=?, updated_at=?, last_error=?, response_json=? WHERE id=?",
            (now, now, message or None, json.dumps(response) if response else None, invoice_id),
        )
    finally:
        conn.close()


def mark_invoice_rejected(invoice_id: int, response: dict[str, Any], message: str) -> None:
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            "UPDATE caea_invoice SET status='rejected', informed_at=?, updated_at=?, last_error=?, response_json=? WHERE id=?",
            (now, now, message, json.dumps(response), invoice_id),
        )
    finally:
        conn.close()


def list_invoices(cuit: int, pto_vta: int | None = None, since_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        sql = "SELECT * FROM caea_invoice WHERE cuit=? AND id>?"
        args: list[Any] = [cuit, since_id]
        if pto_vta is not None:
            sql += " AND pto_vta=?"
            args.append(pto_vta)
        rows = conn.execute(sql + " ORDER BY id LIMIT ?", (*args, limit)).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["response"] = json.loads(item.pop("response_json")) if item.get("response_json") else None
            item.pop("payload_json", None)
            items.append(item)
        return items
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


def set_ptos_venta(cuit: int, ptos_venta: list[int]) -> None:
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM caea_pto_vta WHERE cuit=?", (cuit,))
        conn.executemany("INSERT OR IGNORE INTO caea_pto_vta (cuit, pto_vta) VALUES (?, ?)", [(cuit, int(p)) for p in ptos_venta])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_registered_cuits() -> list[int]:
    conn = get_connection()
    try:
        return [row["cuit"] for row in conn.execute("SELECT DISTINCT cuit FROM caea_pto_vta ORDER BY cuit").fetchall()]
    finally:
        conn.close()


def list_closed_cycles_without_sin_movimiento(today: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT c.id AS cycle_id, c.cuit, p.pto_vta, c.caea_code
              FROM caea_cycle c
              JOIN caea_pto_vta p ON p.cuit = c.cuit
              LEFT JOIN caea_cycle_pv s ON s.cycle_id = c.id AND s.pto_vta = p.pto_vta
             WHERE c.status = 'active' AND c.caea_code IS NOT NULL AND c.fch_vig_hasta < ?
               AND s.sin_movimiento_at IS NULL
               AND NOT EXISTS (SELECT 1 FROM caea_invoice i WHERE i.cycle_id = c.id AND i.pto_vta = p.pto_vta)
             ORDER BY c.id, p.pto_vta
            """,
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_sin_movimiento(cycle_id: int, pto_vta: int, response: dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO caea_cycle_pv (cycle_id, pto_vta, sin_movimiento_at, sin_movimiento_response)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cycle_id, pto_vta) DO UPDATE SET
                sin_movimiento_at=excluded.sin_movimiento_at, sin_movimiento_response=excluded.sin_movimiento_response
            """,
            (cycle_id, pto_vta, _now_iso(), json.dumps(response)),
        )
    finally:
        conn.close()


def list_cycles_with_pvs(cuit: int) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        cycles = [dict(r) for r in conn.execute(
            "SELECT * FROM caea_cycle WHERE cuit=? ORDER BY periodo DESC, orden DESC LIMIT 12", (cuit,)).fetchall()]
        pvs = [r["pto_vta"] for r in conn.execute("SELECT pto_vta FROM caea_pto_vta WHERE cuit=? ORDER BY pto_vta", (cuit,)).fetchall()]
        for cycle in cycles:
            items = []
            for pv in pvs:
                emitted = conn.execute(
                    "SELECT COUNT(*) AS n FROM caea_invoice WHERE cycle_id=? AND pto_vta=?", (cycle["id"], pv)).fetchone()["n"]
                sm = conn.execute(
                    "SELECT * FROM caea_cycle_pv WHERE cycle_id=? AND pto_vta=?", (cycle["id"], pv)).fetchone()
                items.append({
                    "pto_vta": pv,
                    "emitidos": emitted,
                    "sin_movimiento_at": sm["sin_movimiento_at"] if sm else None,
                    "sin_movimiento_response": json.loads(sm["sin_movimiento_response"]) if sm and sm["sin_movimiento_response"] else None,
                })
            cycle["cycle_id"] = cycle.pop("id")
            cycle["ptos_venta"] = items
        return cycles
    finally:
        conn.close()
