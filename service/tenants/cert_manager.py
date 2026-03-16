"""
Certificate manager for AFRelay multitenancy.

Handles:
  - RSA key pair + CSR generation (for AFIP certificate enrollment)
  - Fernet encryption/decryption of private keys stored in the DB
  - Providing cert/key bytes to the SOAP signing layer

AFIP CSR requirements:
  - RSA 2048-bit minimum
  - Subject: CN=<holder name>, SERIALNUMBER=CUIT <cuit>, O=<org>, C=AR
"""
import base64
import hashlib
import os
from datetime import timezone
from typing import Optional

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


# ── Fernet key derivation ──────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    secret = os.getenv("SECRET_KEY", "change-me-this-is-not-secure")
    # Derive a URL-safe base64-encoded 32-byte key from the secret
    derived = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_pem(pem: str) -> str:
    return _get_fernet().encrypt(pem.encode()).decode()


def decrypt_pem(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


# ── Key pair + CSR generation ──────────────────────────────────────────────────

def generate_key_and_csr(
    common_name: str,
    organization: str,
    cuit: str,
    country: str = "AR",
    organizational_unit: str = None,
    email: str = None,
) -> tuple[str, str, str]:
    """
    Generate an RSA 2048 key pair and a CSR ready for AFIP submission.

    Returns:
        (private_key_pem, csr_pem, encrypted_private_key)
    """
    # 1. Generate RSA 2048 private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # 2. Build CSR subject — AFIP requires SERIALNUMBER = "CUIT <cuit>"
    name_attrs = [
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit}"),
    ]
    if organizational_unit:
        name_attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, organizational_unit))

    subject = x509.Name(name_attrs)

    csr_builder = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
    )

    if email:
        csr_builder = csr_builder.add_extension(
            x509.SubjectAlternativeName([x509.RFC822Name(email)]),
            critical=False,
        )

    csr = csr_builder.sign(private_key, hashes.SHA256())

    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()

    # 3. Encrypt private key for DB storage
    encrypted_key = encrypt_pem(private_key_pem)

    return private_key_pem, csr_pem, encrypted_key


# ── Cert loading for SOAP signing ─────────────────────────────────────────────

def get_cert_bytes_for_tenant(tenant_id: int, service: str) -> tuple[bytes, bytes]:
    """
    Load the active certificate and decrypted private key for a tenant/service.
    Returns (cert_bytes, key_bytes) ready for service/crypto/sign.py
    Raises RuntimeError if no active cert exists.
    """
    from service.tenants.db import get_active_cert
    cert_record = get_active_cert(tenant_id, service)
    if not cert_record:
        raise RuntimeError(
            f"No active certificate for tenant {tenant_id}, service '{service}'. "
            "Please upload and activate a certificate in the portal."
        )
    if not cert_record.get("cert_pem"):
        raise RuntimeError(
            f"Certificate for tenant {tenant_id}, service '{service}' has not been "
            "uploaded yet. Submit the CSR to AFIP and upload the returned certificate."
        )
    if not cert_record.get("private_key_encrypted"):
        raise RuntimeError(
            f"Private key missing for tenant {tenant_id}, service '{service}'."
        )

    cert_bytes = cert_record["cert_pem"].encode()
    key_pem = decrypt_pem(cert_record["private_key_encrypted"])
    key_bytes = key_pem.encode()

    return cert_bytes, key_bytes


# ── Certificate parsing ────────────────────────────────────────────────────────

def parse_cert_expiry(cert_pem: str) -> Optional[str]:
    """Extract the expiry date from a PEM certificate. Returns ISO string or None."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        expires = cert.not_valid_after_utc
        return expires.isoformat()
    except Exception:
        try:
            # Fallback for older cryptography versions
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            expires = cert.not_valid_after
            return expires.replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            return None


def validate_cert_pem(cert_pem: str) -> tuple[bool, str]:
    """Validate a PEM certificate. Returns (is_valid, message)."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        subject = cert.subject.rfc4514_string()
        try:
            expires = cert.not_valid_after_utc
        except Exception:
            from datetime import timezone as tz
            expires = cert.not_valid_after.replace(tzinfo=tz.utc)
        from datetime import datetime
        if expires < datetime.now(timezone.utc):
            return False, f"Certificate expired on {expires.isoformat()}"
        return True, f"Valid. Subject: {subject}. Expires: {expires.isoformat()}"
    except Exception as e:
        return False, f"Invalid certificate: {e}"
