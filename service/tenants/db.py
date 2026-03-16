"""
Multi-tenant SQLite database for AFRelay.
Manages tenants, service pricing, balance ledger, WSAA tokens, and certificates.
"""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("AFRELAY_TENANTS_DB", "service/state/afrelay_tenants.db"))

DEFAULT_PRICES = [
    ("wsaa_token",           0.00, "WSAA token renewal"),
    ("wsfe_invoice",         0.10, "CAE invoice authorization (FECAESolicitar)"),
    ("wsfe_query",           0.02, "Invoice query (FECompConsultar)"),
    ("wsfe_last_authorized", 0.02, "Last authorized invoice number"),
    ("wsfe_params",          0.01, "WSFE parameter lookups"),
    ("wspci_token",          0.00, "WSPCI token renewal"),
    ("wspci_persona",        0.05, "Taxpayer persona query"),
    ("wsfe_caea_solicitar",  0.05, "CAEA solicit"),
    ("wsfe_caea_informar",   0.05, "CAEA inform movement"),
    ("wsfe_caea_consultar",  0.02, "CAEA query"),
    ("wsfe_caea_queue",      0.10, "CAEA resilience queue operations"),
]


def _ensure_db_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT NOT NULL,
                email             TEXT NOT NULL UNIQUE,
                hashed_password   TEXT NOT NULL,
                cuit              TEXT,
                api_key_hash      TEXT NOT NULL UNIQUE,
                balance           REAL NOT NULL DEFAULT 0.0,
                is_active         INTEGER NOT NULL DEFAULT 1,
                env_flags         TEXT NOT NULL DEFAULT '{}',
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL,
                notes             TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS service_prices (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL UNIQUE,
                price        REAL NOT NULL DEFAULT 0.0,
                description  TEXT,
                is_active    INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS balance_transactions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id     INTEGER NOT NULL REFERENCES tenants(id),
                type          TEXT NOT NULL,
                amount        REAL NOT NULL,
                balance_after REAL NOT NULL,
                service_name  TEXT,
                reference     TEXT,
                created_at    TEXT NOT NULL,
                notes         TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_tokens (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id   INTEGER NOT NULL REFERENCES tenants(id),
                service     TEXT NOT NULL,
                token       TEXT,
                sign        TEXT,
                expires_at  TEXT,
                updated_at  TEXT,
                UNIQUE(tenant_id, service)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_certs (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id             INTEGER NOT NULL REFERENCES tenants(id),
                service               TEXT NOT NULL,
                label                 TEXT,
                common_name           TEXT,
                organization          TEXT,
                country               TEXT DEFAULT 'AR',
                cuit                  TEXT,
                private_key_encrypted TEXT,
                csr_pem               TEXT,
                cert_pem              TEXT,
                cert_expires_at       TEXT,
                status                TEXT NOT NULL DEFAULT 'pending_key',
                is_active             INTEGER NOT NULL DEFAULT 0,
                created_at            TEXT NOT NULL,
                updated_at            TEXT NOT NULL,
                notes                 TEXT
            )
        """)
        _seed_prices(conn)
    finally:
        conn.close()

    # Migrate existing CAEA tables if needed
    _migrate_caea_tables()


def _seed_prices(conn: sqlite3.Connection):
    for name, price, desc in DEFAULT_PRICES:
        conn.execute(
            "INSERT OR IGNORE INTO service_prices (service_name, price, description) VALUES (?,?,?)",
            (name, price, desc),
        )


def _migrate_caea_tables():
    """Add tenant_id to existing CAEA tables if missing."""
    from service.caea_resilience.db import DB_PATH as CAEA_DB
    if not CAEA_DB.exists():
        return
    try:
        conn = sqlite3.connect(CAEA_DB, timeout=10.0, isolation_level=None)
        for table in ("caea_cycle", "caea_invoice", "afip_outbox"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "tenant_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER")
        conn.close()
    except Exception:
        pass


# ── Auth helpers ───────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def generate_api_key() -> tuple[str, str]:
    """Returns (plain_key, sha256_hash). Only the hash is stored."""
    plain = "afr_" + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    return plain, hashed


# ── Tenant CRUD ────────────────────────────────────────────────────────────────

def create_tenant(
    name: str, email: str, password: str,
    cuit: str = None, balance: float = 0.0,
    notes: str = None, is_active: bool = True,
    env_flags: dict = None,
) -> tuple[dict, str]:
    """Returns (tenant_row, plain_api_key)."""
    plain_key, key_hash = generate_api_key()
    hashed_pw = hash_password(password)
    now = _now()
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO tenants
              (name, email, hashed_password, cuit, api_key_hash,
               balance, is_active, env_flags, created_at, updated_at, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (name, email.lower(), hashed_pw, cuit, key_hash,
              balance, 1 if is_active else 0,
              json.dumps(env_flags or {}), now, now, notes))
        return _row_to_dict(conn.execute("SELECT * FROM tenants WHERE id=?", (cur.lastrowid,)).fetchone()), plain_key
    finally:
        conn.close()


def get_tenant_by_id(tenant_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_tenant_by_email(email: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tenants WHERE email=?", (email.lower(),)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_tenant_by_api_key_hash(api_key_hash: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tenants WHERE api_key_hash=?", (api_key_hash,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_tenants(include_inactive: bool = False) -> list[dict]:
    conn = get_connection()
    try:
        q = "SELECT * FROM tenants"
        if not include_inactive:
            q += " WHERE is_active=1"
        q += " ORDER BY created_at DESC"
        return [_row_to_dict(r) for r in conn.execute(q).fetchall()]
    finally:
        conn.close()


def update_tenant(tenant_id: int, **kwargs) -> Optional[dict]:
    allowed = {"name", "email", "cuit", "is_active", "env_flags", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_tenant_by_id(tenant_id)
    updates["updated_at"] = _now()
    if "env_flags" in updates and isinstance(updates["env_flags"], dict):
        updates["env_flags"] = json.dumps(updates["env_flags"])
    if "email" in updates:
        updates["email"] = updates["email"].lower()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn = get_connection()
    try:
        conn.execute(f"UPDATE tenants SET {set_clause} WHERE id=?", list(updates.values()) + [tenant_id])
        return get_tenant_by_id(tenant_id)
    finally:
        conn.close()


def rotate_api_key(tenant_id: int) -> tuple[Optional[dict], str]:
    plain_key, key_hash = generate_api_key()
    conn = get_connection()
    try:
        conn.execute("UPDATE tenants SET api_key_hash=?, updated_at=? WHERE id=?",
                     (key_hash, _now(), tenant_id))
        return get_tenant_by_id(tenant_id), plain_key
    finally:
        conn.close()


def update_password(tenant_id: int, new_password: str):
    conn = get_connection()
    try:
        conn.execute("UPDATE tenants SET hashed_password=?, updated_at=? WHERE id=?",
                     (hash_password(new_password), _now(), tenant_id))
    finally:
        conn.close()


def get_all_active_tenants() -> list[dict]:
    return list_tenants(include_inactive=False)


# ── Balance / Billing ──────────────────────────────────────────────────────────

def get_service_price(service_name: str) -> float:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT price FROM service_prices WHERE service_name=? AND is_active=1",
            (service_name,),
        ).fetchone()
        return float(row["price"]) if row else 0.0
    finally:
        conn.close()


def list_service_prices() -> list[dict]:
    conn = get_connection()
    try:
        return [_row_to_dict(r) for r in conn.execute(
            "SELECT * FROM service_prices ORDER BY service_name"
        ).fetchall()]
    finally:
        conn.close()


def update_service_price(service_name: str, price: float) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE service_prices SET price=? WHERE service_name=?",
            (price, service_name),
        )
        return cur.rowcount > 0
    finally:
        conn.close()


def credit_balance(tenant_id: int, amount: float, reference: str = None, notes: str = None) -> float:
    if amount <= 0:
        raise ValueError("Credit amount must be positive")
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        row = conn.execute("SELECT balance FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if not row:
            raise ValueError(f"Tenant {tenant_id} not found")
        new_balance = round(row["balance"] + amount, 6)
        conn.execute("UPDATE tenants SET balance=?, updated_at=? WHERE id=?",
                     (new_balance, _now(), tenant_id))
        conn.execute("""
            INSERT INTO balance_transactions
              (tenant_id, type, amount, balance_after, reference, created_at, notes)
            VALUES (?,'credit',?,?,?,?,?)
        """, (tenant_id, amount, new_balance, reference, _now(), notes))
        conn.execute("COMMIT")
        return new_balance
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def debit_balance(tenant_id: int, service_name: str, amount: float, reference: str = None) -> float:
    if amount <= 0:
        t = get_tenant_by_id(tenant_id)
        return t["balance"] if t else 0.0
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        row = conn.execute("SELECT balance FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if not row:
            raise ValueError(f"Tenant {tenant_id} not found")
        new_balance = round(row["balance"] - amount, 6)
        conn.execute("UPDATE tenants SET balance=?, updated_at=? WHERE id=?",
                     (new_balance, _now(), tenant_id))
        conn.execute("""
            INSERT INTO balance_transactions
              (tenant_id, type, amount, balance_after, service_name, reference, created_at)
            VALUES (?,'debit',?,?,?,?,?)
        """, (tenant_id, amount, new_balance, service_name, reference, _now()))
        conn.execute("COMMIT")
        return new_balance
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def list_transactions(tenant_id: int, limit: int = 100, offset: int = 0) -> list[dict]:
    conn = get_connection()
    try:
        return [_row_to_dict(r) for r in conn.execute("""
            SELECT * FROM balance_transactions WHERE tenant_id=?
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """, (tenant_id, limit, offset)).fetchall()]
    finally:
        conn.close()


def get_usage_summary(tenant_id: int) -> list[dict]:
    conn = get_connection()
    try:
        return [_row_to_dict(r) for r in conn.execute("""
            SELECT service_name, COUNT(*) as call_count, SUM(amount) as total_spent
            FROM balance_transactions WHERE tenant_id=? AND type='debit'
            GROUP BY service_name ORDER BY total_spent DESC
        """, (tenant_id,)).fetchall()]
    finally:
        conn.close()


def get_admin_stats() -> dict:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM tenants WHERE is_active=1").fetchone()[0]
        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM balance_transactions WHERE type='credit'"
        ).fetchone()[0]
        calls_today = conn.execute("""
            SELECT COUNT(*) FROM balance_transactions
            WHERE type='debit' AND created_at >= date('now')
        """).fetchone()[0]
        return {"total_tenants": total, "active_tenants": active,
                "total_revenue": revenue, "calls_today": calls_today}
    finally:
        conn.close()


# ── Token store ────────────────────────────────────────────────────────────────

def save_tenant_token(tenant_id: int, service: str, token: str, sign: str, expires_at: str):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO tenant_tokens (tenant_id, service, token, sign, expires_at, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(tenant_id, service) DO UPDATE SET
              token=excluded.token, sign=excluded.sign,
              expires_at=excluded.expires_at, updated_at=excluded.updated_at
        """, (tenant_id, service, token, sign, expires_at, _now()))
    finally:
        conn.close()


def get_tenant_token(tenant_id: int, service: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM tenant_tokens WHERE tenant_id=? AND service=?",
            (tenant_id, service),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def is_token_expiring_soon(tenant_id: int, service: str, minutes: int = 30) -> bool:
    token = get_tenant_token(tenant_id, service)
    if not token or not token.get("expires_at"):
        return True
    try:
        expires = datetime.fromisoformat(token["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        threshold = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return expires <= threshold
    except Exception:
        return True


def is_token_expired(tenant_id: int, service: str) -> bool:
    return is_token_expiring_soon(tenant_id, service, minutes=0)


def list_all_tokens() -> list[dict]:
    conn = get_connection()
    try:
        return [_row_to_dict(r) for r in conn.execute("""
            SELECT tt.*, t.name as tenant_name, t.cuit
            FROM tenant_tokens tt JOIN tenants t ON t.id = tt.tenant_id
            ORDER BY tt.tenant_id, tt.service
        """).fetchall()]
    finally:
        conn.close()


# ── Cert store ─────────────────────────────────────────────────────────────────

def create_cert_record(
    tenant_id: int, service: str, common_name: str,
    organization: str, country: str, cuit: str,
    private_key_encrypted: str, csr_pem: str, label: str = None,
) -> dict:
    conn = get_connection()
    try:
        now = _now()
        cur = conn.execute("""
            INSERT INTO tenant_certs
              (tenant_id, service, label, common_name, organization, country, cuit,
               private_key_encrypted, csr_pem, status, is_active, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,'pending_cert',0,?,?)
        """, (tenant_id, service, label, common_name, organization, country, cuit,
              private_key_encrypted, csr_pem, now, now))
        row = conn.execute("SELECT * FROM tenant_certs WHERE id=?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def upload_cert(cert_id: int, cert_pem: str) -> Optional[dict]:
    from service.tenants.cert_manager import parse_cert_expiry
    expires_at = parse_cert_expiry(cert_pem)
    conn = get_connection()
    try:
        now = _now()
        conn.execute("""
            UPDATE tenant_certs SET cert_pem=?, cert_expires_at=?, status='ready', updated_at=?
            WHERE id=?
        """, (cert_pem, expires_at, now, cert_id))
        row = conn.execute("SELECT * FROM tenant_certs WHERE id=?", (cert_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def activate_cert(cert_id: int) -> bool:
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        cert = conn.execute("SELECT * FROM tenant_certs WHERE id=?", (cert_id,)).fetchone()
        if not cert or cert["status"] not in ("ready", "active"):
            conn.execute("ROLLBACK")
            return False
        conn.execute(
            "UPDATE tenant_certs SET is_active=0, updated_at=? WHERE tenant_id=? AND service=?",
            (_now(), cert["tenant_id"], cert["service"]),
        )
        conn.execute(
            "UPDATE tenant_certs SET is_active=1, status='active', updated_at=? WHERE id=?",
            (_now(), cert_id),
        )
        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def get_active_cert(tenant_id: int, service: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT * FROM tenant_certs
            WHERE tenant_id=? AND service=? AND is_active=1
            ORDER BY updated_at DESC LIMIT 1
        """, (tenant_id, service)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_tenant_certs(tenant_id: int) -> list[dict]:
    conn = get_connection()
    try:
        return [_row_to_dict(r) for r in conn.execute(
            "SELECT * FROM tenant_certs WHERE tenant_id=? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()]
    finally:
        conn.close()


def get_cert_by_id(cert_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tenant_certs WHERE id=?", (cert_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_cert(cert_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM tenant_certs WHERE id=?", (cert_id,))
    finally:
        conn.close()


# ── Internal ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    if "env_flags" in d and isinstance(d["env_flags"], str):
        try:
            d["env_flags"] = json.loads(d["env_flags"])
        except Exception:
            d["env_flags"] = {}
    return d
