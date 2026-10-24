"""Initial numbering of CAEA points of sale, read from ARCA while it is reachable.

A CAEA PV has its own numbering. The first local number is ARCA's last authorized + 1;
that value is seeded into caea_numbering while ARCA is online (PUT ptos-venta and the
periodic bootstrap) so the first contingency invoice can be issued with ARCA down.
"""
import os
from typing import Any

from service.caea_resilience import repository as repo
from service.controllers.request_last_authorized_controller import \
    get_last_authorized_info
from service.utils.logger import logger

DEFAULT_CBTE_TIPOS = "1,3,6,8"


class LastAuthorizedUnavailable(RuntimeError):
    """ARCA's last authorized number could not be read (short, client-safe message)."""


def configured_cbte_tipos() -> list[int]:
    values = []
    for chunk in os.getenv("CAEA_CBTE_TIPOS", DEFAULT_CBTE_TIPOS).split(","):
        piece = chunk.strip()
        if not piece:
            continue
        try:
            values.append(int(piece))
        except ValueError:
            logger.warning("Ignoring invalid voucher type in CAEA_CBTE_TIPOS: %s", piece)
    return list(dict.fromkeys(values))


def _error_codes(response: dict[str, Any]) -> list[str]:
    errors = (response or {}).get("Errors")
    err = errors.get("Err") if isinstance(errors, dict) else None
    if isinstance(err, dict):
        err = [err]
    return [str(e.get("Code")) for e in (err or []) if isinstance(e, dict)]


async def read_last_authorized(cuit: int, pto_vta: int, cbte_tipo: int) -> int:
    """FECompUltimoAutorizado for one PV/type. Raises LastAuthorizedUnavailable."""
    try:
        last = await get_last_authorized_info({"Cuit": cuit, "PtoVta": pto_vta, "CbteTipo": cbte_tipo})
    except Exception as exc:  # token file missing/invalid, unexpected client errors
        logger.warning("FECompUltimoAutorizado raised cuit=%s pv=%s tipo=%s: %r", cuit, pto_vta, cbte_tipo, exc)
        raise LastAuthorizedUnavailable(f"ARCA token/cliente no disponible ({type(exc).__name__})") from exc
    if not isinstance(last, dict) or last.get("status") != "success":
        error = (last or {}).get("error") if isinstance(last, dict) else None
        kind = error.get("error_type") if isinstance(error, dict) else None
        logger.warning("FECompUltimoAutorizado failed cuit=%s pv=%s tipo=%s: %s", cuit, pto_vta, cbte_tipo, last)
        raise LastAuthorizedUnavailable(f"ARCA no disponible ({kind or 'error'})")
    response = last.get("response") or {}
    codes = _error_codes(response)
    if codes:
        logger.warning("FECompUltimoAutorizado errors cuit=%s pv=%s tipo=%s: %s", cuit, pto_vta, cbte_tipo, response)
        raise LastAuthorizedUnavailable(f"ARCA respondio con errores ({', '.join(codes[:5])})")
    if response.get("CbteNro") is None:
        raise LastAuthorizedUnavailable("ARCA no informo el ultimo comprobante autorizado")
    return int(response["CbteNro"])


async def seed_numbering(cuit: int) -> dict[str, Any]:
    """Seed caea_numbering for every registered CAEA PV x CAEA_CBTE_TIPOS. Never raises."""
    summary: dict[str, Any] = {"seeded": 0, "skipped": 0, "errors": []}
    try:
        ptos_venta = repo.list_ptos_venta(cuit)
    except Exception as exc:
        logger.warning("CAEA numbering seed: cannot list ptos venta cuit=%s: %r", cuit, exc)
        summary["errors"].append({"pto_vta": None, "cbte_tipo": None, "error": type(exc).__name__})
        return summary
    for pto_vta in ptos_venta:
        for cbte_tipo in configured_cbte_tipos():
            try:
                if repo.has_local_invoices(cuit, pto_vta, cbte_tipo):
                    summary["skipped"] += 1  # local MAX rules from now on; no ARCA call needed
                    continue
                last = await read_last_authorized(cuit, pto_vta, cbte_tipo)
                if repo.seed_numbering(cuit, pto_vta, cbte_tipo, last):
                    summary["seeded"] += 1
                else:
                    summary["skipped"] += 1
            except LastAuthorizedUnavailable as exc:
                summary["errors"].append({"pto_vta": pto_vta, "cbte_tipo": cbte_tipo, "error": str(exc)})
            except Exception as exc:
                logger.warning("CAEA numbering seed failed cuit=%s pv=%s tipo=%s: %r", cuit, pto_vta, cbte_tipo, exc)
                summary["errors"].append({"pto_vta": pto_vta, "cbte_tipo": cbte_tipo, "error": type(exc).__name__})
    if summary["errors"]:
        logger.warning("CAEA numbering seed cuit=%s: %s", cuit, summary)
    return summary
