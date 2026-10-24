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
        for column in ("informed_at", "response_json"):
            if column not in existing:
                conn.execute(f"ALTER TABLE caea_invoice ADD COLUMN {column} TEXT")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_caea_invoice
            ON caea_invoice (cuit, pto_vta, cbte_tipo, cbte_nro);
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

