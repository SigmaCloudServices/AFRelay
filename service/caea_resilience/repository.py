import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from service.caea_resilience.db import get_connection

INFORM_JOB = "INFORM_CAEA_MOVEMENT"


def _iso(moment: datetime) -> str:
    # Fixed width (always microseconds, always +00:00) so stored timestamps compare as strings.
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _now_iso() -> str:
    return _iso(datetime.now(timezone.utc))


def normalize_timestamp(value: str) -> str:
    """Parse an ISO timestamp (offset or Z; naive = UTC) into the stored UTC format. ValueError if invalid."""
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _iso(parsed)


def inform_idempotency_key(cuit: int, pto_vta: int, cbte_tipo: int, cbte_nro: int) -> str:
    return f"inform:{cuit}:{pto_vta}:{cbte_tipo}:{cbte_nro}"


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


def get_numbering(cuit: int, pto_vta: int, cbte_tipo: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM caea_numbering WHERE cuit=? AND pto_vta=? AND cbte_tipo=?",
            (cuit, pto_vta, cbte_tipo),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def seed_numbering(cuit: int, pto_vta: int, cbte_tipo: int, last_nro: int) -> bool:
    """Store ARCA's last authorized number for a CAEA PV/type.

    Only while there are no local invoices for that key (afterwards local MAX rules).
    Returns True when the seed was written.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        local = conn.execute(
            "SELECT 1 FROM caea_invoice WHERE cuit=? AND pto_vta=? AND cbte_tipo=? LIMIT 1",
            (cuit, pto_vta, cbte_tipo),
        ).fetchone()
        if local is None:
            conn.execute(
                """
                INSERT INTO caea_numbering (cuit, pto_vta, cbte_tipo, last_nro, seeded_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cuit, pto_vta, cbte_tipo) DO UPDATE SET
                    last_nro=excluded.last_nro, seeded_at=excluded.seeded_at
                """,
                (cuit, pto_vta, cbte_tipo, int(last_nro), _now_iso()),
            )
        conn.commit()
        return local is None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_invoice_by_client_ref(cuit: int, client_ref: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM caea_invoice WHERE cuit=? AND client_ref=?", (cuit, client_ref)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_outbox_job_by_key(idempotency_key: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM afip_outbox WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def issue_local_invoice(
    cycle_id: int,
    cuit: int,
    pto_vta: int,
    cbte_tipo: int,
    payload: dict[str, Any],
    seed_last_nro: int | None,
    client_ref: str | None = None,
) -> dict[str, Any]:
    """Reserve the next number, insert the invoice and its inform job in one IMMEDIATE transaction.

    Numbering: MAX(local) -> caea_numbering.last_nro -> seed_last_nro (ARCA live) -> 0.
    With client_ref, an existing (cuit, client_ref) invoice is returned unchanged (idempotent retry).
    The caller's payload is not mutated; the stored payload (PtoVta/CbteTipo/CantReg=1, number,
    CAEA of the cycle) is the request the outbox informs.
    """
    payload = copy.deepcopy(payload)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if client_ref is not None:
            existing = conn.execute(
                "SELECT * FROM caea_invoice WHERE cuit=? AND client_ref=?", (cuit, client_ref)).fetchone()
            if existing is not None:
                conn.commit()
                return dict(existing)
        row = conn.execute(
            "SELECT MAX(cbte_nro) AS max_nro FROM caea_invoice WHERE cuit=? AND pto_vta=? AND cbte_tipo=?",
            (cuit, pto_vta, cbte_tipo),
        ).fetchone()
        if row["max_nro"] is not None:
            last = int(row["max_nro"])
        else:
            seeded = conn.execute(
                "SELECT last_nro FROM caea_numbering WHERE cuit=? AND pto_vta=? AND cbte_tipo=?",
                (cuit, pto_vta, cbte_tipo),
            ).fetchone()
            last = int(seeded["last_nro"]) if seeded is not None else int(seed_last_nro or 0)
        cbte_nro = last + 1

        cab = payload.get("FeCabReq")
        if not isinstance(cab, dict):
            cab = payload["FeCabReq"] = {}
        cab.update({"CantReg": 1, "PtoVta": pto_vta, "CbteTipo": cbte_tipo})
        det = payload["FeDetReq"]["FECAEADetRequest"][0]
        det["CbteDesde"] = cbte_nro
        det["CbteHasta"] = cbte_nro
        cycle = conn.execute("SELECT caea_code FROM caea_cycle WHERE id=?", (cycle_id,)).fetchone()
        if cycle is not None and cycle["caea_code"]:
            det["CAEA"] = cycle["caea_code"]

        now = _now_iso()
        stored_payload = json.dumps(payload)
        conn.execute(
            """
            INSERT INTO caea_invoice
                (cycle_id, cuit, pto_vta, cbte_tipo, cbte_nro, payload_json, status, created_at, updated_at, client_ref)
            VALUES (?, ?, ?, ?, ?, ?, 'issued_local', ?, ?, ?)
            """,
            (cycle_id, cuit, pto_vta, cbte_tipo, cbte_nro, stored_payload, now, now, client_ref),
        )
        inserted = dict(conn.execute("SELECT * FROM caea_invoice WHERE id = last_insert_rowid()").fetchone())
        job_payload = {
            "invoice_id": inserted["id"],
            "request": {"Cuit": cuit, "FeCAEARegInfReq": json.loads(inserted["payload_json"])},
        }
        conn.execute(
            """
            INSERT INTO afip_outbox
                (job_type, idempotency_key, payload_json, status, attempts, next_retry_at, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
            """,
            (INFORM_JOB, inform_idempotency_key(cuit, pto_vta, cbte_tipo, cbte_nro),
             json.dumps(job_payload), now, now, now),
        )
        conn.commit()
        return inserted
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
            "UPDATE caea_invoice SET status='informed', informed_at=?, updated_at=?, last_error=?, response_json=? WHERE id=? AND status NOT IN ('informed', 'rejected')",
            (now, now, message or None, json.dumps(response) if response else None, invoice_id),
        )
    finally:
        conn.close()


def mark_invoice_rejected(invoice_id: int, response: dict[str, Any], message: str) -> None:
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            "UPDATE caea_invoice SET status='rejected', informed_at=?, updated_at=?, last_error=?, response_json=? WHERE id=? AND status NOT IN ('informed', 'rejected')",
            (now, now, message, json.dumps(response), invoice_id),
        )
    finally:
        conn.close()


def public_invoice(row: dict[str, Any]) -> dict[str, Any]:
    """Invoice as exposed by the API: response parsed, stored request not echoed."""
    item = dict(row)
    item["response"] = json.loads(item.pop("response_json")) if item.get("response_json") else None
    item.pop("payload_json", None)
    return item


def list_invoices(
    cuit: int,
    pto_vta: int | None = None,
    since_id: int = 0,
    limit: int = 200,
    updated_since: str | None = None,
    cbte_tipo: int | None = None,
    cbte_nro: int | None = None,
) -> list[dict[str, Any]]:
    """List invoices.

    Without updated_since: id cursor (id > since_id, ORDER BY id) -- new invoices only.
    With updated_since: keyset cursor over (updated_at, id) -- every status change.
    Rows with updated_at > updated_since, or updated_at == updated_since and id > since_id,
    ORDER BY updated_at, id. Pass back the last item's updated_at and id as the next cursor.
    updated_since must already be normalised (normalize_timestamp).
    """
    conn = get_connection()
    try:
        sql = "SELECT * FROM caea_invoice WHERE cuit=?"
        args: list[Any] = [cuit]
        if updated_since is not None:
            sql += " AND (updated_at > ? OR (updated_at = ? AND id > ?))"
            args += [updated_since, updated_since, since_id]
            order = " ORDER BY updated_at, id"
        else:
            sql += " AND id > ?"
            args.append(since_id)
            order = " ORDER BY id"
        for column, value in (("pto_vta", pto_vta), ("cbte_tipo", cbte_tipo), ("cbte_nro", cbte_nro)):
            if value is not None:
                sql += f" AND {column}=?"
                args.append(value)
        rows = conn.execute(sql + order + " LIMIT ?", (*args, limit)).fetchall()
        return [public_invoice(dict(row)) for row in rows]
    finally:
        conn.close()


def note_invoice_inform_error(invoice_id: int, error: str) -> None:
    """Transient inform failure: the invoice stays 'issued_local', only last_error is recorded."""
    conn = get_connection()
    try:
        conn.execute(
            # updated_at only moves when the message changes, so updated_since pollers are not flooded.
            "UPDATE caea_invoice SET last_error=?, updated_at=? WHERE id=? AND status='issued_local' AND last_error IS NOT ?",
            (error, _now_iso(), invoice_id, error),
        )
    finally:
        conn.close()


def mark_invoice_error(invoice_id: int, error: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE caea_invoice SET status='error', updated_at=?, last_error=? WHERE id=? AND status NOT IN ('informed', 'rejected')",
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


def claim_outbox_job(job_id: int) -> dict[str, Any] | None:
    """Atomically move a due job to 'processing' and return its fresh row.

    None when another runner already claimed it (or rescheduled it into the future):
    the caller must skip the job.
    """
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            UPDATE afip_outbox SET status='processing', updated_at=?
             WHERE id=? AND status IN ('pending', 'retrying') AND next_retry_at <= ?
            """,
            (now, job_id, now),
        )
        row = conn.execute("SELECT * FROM afip_outbox WHERE id=?", (job_id,)).fetchone() if cur.rowcount == 1 else None
        conn.commit()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_outbox_done(job_id: int, response: dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE afip_outbox
               SET status='done', updated_at=?, last_error=NULL, last_response_json=?
             WHERE id=? AND status='processing'
            """,
            (_now_iso(), json.dumps(response), job_id),
        )
    finally:
        conn.close()


DEFAULT_MAX_ATTEMPTS = 10


def mark_outbox_retry(job_id: int, attempts: int, next_retry_at: str, error: str,
                      max_attempts: int | None = DEFAULT_MAX_ATTEMPTS) -> str:
    """Record a failed attempt. max_attempts=None means retry forever. Returns the new status."""
    conn = get_connection()
    try:
        status = "failed" if max_attempts is not None and attempts >= max_attempts else "retrying"
        conn.execute(
            """
            UPDATE afip_outbox
               SET status=?, attempts=?, next_retry_at=?, last_error=?, updated_at=?
             WHERE id=? AND status='processing'
            """,
            (status, attempts, next_retry_at, error, _now_iso(), job_id),
        )
        return status
    finally:
        conn.close()


def recover_stranded_processing_jobs(older_than_minutes: int = 10) -> int:
    """Jobs left in 'processing' by a crashed runner go back to 'retrying', due now.

    Safe alongside live runners: the atomic claim prevents a double run, and a live
    job never stays in 'processing' for minutes (SOAP calls time out well before).
    """
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc)
        cutoff = _iso(now - timedelta(minutes=older_than_minutes))
        cur = conn.execute(
            """
            UPDATE afip_outbox SET status='retrying', next_retry_at=?, updated_at=?,
                   last_error=COALESCE(last_error, 'recovered from stranded processing')
             WHERE status='processing' AND updated_at < ?
            """,
            (_iso(now), _iso(now), cutoff),
        )
        return cur.rowcount
    finally:
        conn.close()


def revive_failed_outbox_jobs() -> int:
    """Put every 'failed' job back to 'pending' (attempts reset to 0, due now).

    Invoices whose inform job had died ('error') go back to 'issued_local' because
    their inform is pending again.
    """
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT id, job_type, payload_json FROM afip_outbox WHERE status='failed'").fetchall()
        for row in rows:
            conn.execute(
                "UPDATE afip_outbox SET status='pending', attempts=0, next_retry_at=?, updated_at=? WHERE id=?",
                (now, now, row["id"]),
            )
            if row["job_type"] == "INFORM_CAEA_MOVEMENT":
                invoice_id = json.loads(row["payload_json"]).get("invoice_id")
                conn.execute(
                    "UPDATE caea_invoice SET status='issued_local', updated_at=? WHERE id=? AND status='error'",
                    (now, invoice_id),
                )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
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


def list_ptos_venta(cuit: int) -> list[int]:
    conn = get_connection()
    try:
        return [row["pto_vta"] for row in conn.execute(
            "SELECT pto_vta FROM caea_pto_vta WHERE cuit=? ORDER BY pto_vta", (cuit,)).fetchall()]
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
            SELECT c.id AS cycle_id, c.cuit, p.pto_vta, c.caea_code, c.fch_tope_inf
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
