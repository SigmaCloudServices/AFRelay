import calendar
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("AFRELAY_STATE_DB", "service/state/afrelay_state.db"))


def _ensure_db_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _backfill_cycle_validity(conn: sqlite3.Connection) -> None:
    """Derive validity dates of active cycles created before those columns existed.

    orden 1 -> days 01..15, orden 2 -> day 16..last day of month (YYYYMMDD).
    fch_tope_inf stays NULL: only ARCA knows it. Idempotent (only NULL rows).
    """
    rows = conn.execute(
        """
        SELECT id, periodo, orden FROM caea_cycle
         WHERE status='active' AND (fch_vig_desde IS NULL OR fch_vig_hasta IS NULL)
        """
    ).fetchall()
    for row in rows:
        periodo, orden = int(row["periodo"]), int(row["orden"])
        year, month = divmod(periodo, 100)
        if not 1 <= month <= 12 or orden not in (1, 2):
            continue
        if orden == 1:
            desde, hasta = f"{periodo}01", f"{periodo}15"
        else:
            desde, hasta = f"{periodo}16", f"{periodo}{calendar.monthrange(year, month)[1]:02d}"
        conn.execute(
            """
            UPDATE caea_cycle
               SET fch_vig_desde=COALESCE(fch_vig_desde, ?), fch_vig_hasta=COALESCE(fch_vig_hasta, ?)
             WHERE id=?
            """,
            (desde, hasta, row["id"]),
        )


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caea_cycle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cuit INTEGER NOT NULL,
                periodo INTEGER NOT NULL,
                orden INTEGER NOT NULL,
                caea_code TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT
            );
            """
        )
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(caea_cycle)").fetchall()}
        for column in ("fch_vig_desde", "fch_vig_hasta", "fch_tope_inf"):
            if column not in existing:
                conn.execute(f"ALTER TABLE caea_cycle ADD COLUMN {column} TEXT")
        _backfill_cycle_validity(conn)
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_caea_cycle
            ON caea_cycle (cuit, periodo, orden);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caea_invoice (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                cuit INTEGER NOT NULL,
                pto_vta INTEGER NOT NULL,
                cbte_tipo INTEGER NOT NULL,
                cbte_nro INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT,
                FOREIGN KEY (cycle_id) REFERENCES caea_cycle(id)
            );
            """
        )
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(caea_invoice)").fetchall()}
        for column in ("informed_at", "response_json", "client_ref"):
            if column not in existing:
                conn.execute(f"ALTER TABLE caea_invoice ADD COLUMN {column} TEXT")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_caea_invoice
            ON caea_invoice (cuit, pto_vta, cbte_tipo, cbte_nro);
            """
        )
        # NULL client_ref values never collide (SQLite UNIQUE treats NULLs as distinct).
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_caea_invoice_client_ref
            ON caea_invoice (cuit, client_ref);
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_caea_invoice_updated ON caea_invoice (cuit, updated_at, id);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caea_numbering (
                cuit INTEGER NOT NULL,
                pto_vta INTEGER NOT NULL,
                cbte_tipo INTEGER NOT NULL,
                last_nro INTEGER NOT NULL,
                seeded_at TEXT NOT NULL,
                PRIMARY KEY (cuit, pto_vta, cbte_tipo)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS afip_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT,
                last_response_json TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caea_pto_vta (
                cuit INTEGER NOT NULL,
                pto_vta INTEGER NOT NULL,
                PRIMARY KEY (cuit, pto_vta)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caea_cycle_pv (
                cycle_id INTEGER NOT NULL,
                pto_vta INTEGER NOT NULL,
                sin_movimiento_at TEXT,
                sin_movimiento_response TEXT,
                PRIMARY KEY (cycle_id, pto_vta)
            );
            """
        )
    finally:
        conn.close()

