# CAEA contingency: contract for simpos

AFRelay issues CAEA vouchers locally while ARCA is unreachable and informs them
(`FECAEARegInformativo`) from a durable outbox when ARCA is back. All endpoints
need the usual JWT (`Authorization: Bearer ...`).

## Endpoints

| Method / path | Use |
|---|---|
| `PUT /wsfe/caea/queue/ptos-venta` | Register the CAEA points of sale of a CUIT. Body `{"Cuit", "PtosVenta": [int]}`. Also ensures the current/next cycles and seeds numbering (see below). Always `200` with `seeding: {"seeded", "skipped", "errors": [{"pto_vta", "cbte_tipo", "error"}]}`; seeding failures never fail the PUT. |
| `GET /wsfe/caea/queue/active?cuit=` | The two cycles of "today" (current + next): `cycle_id, periodo, orden, fch_vig_desde, fch_vig_hasta, fch_tope_inf, active, caea_code, status`. |
| `GET /wsfe/caea/queue/cycles?cuit=` | Last 12 cycles with, per registered PV, `emitidos` and `sin_movimiento_at`. |
| `POST /wsfe/caea/queue/issue-local` | Issue one voucher with the CAEA of its date. See below. |
| `GET /wsfe/caea/queue/invoices?cuit=` | Invoice states (see cursors). Filters: `pto_vta`, `cbte_tipo`, `cbte_nro`, `limit` (1..500, default 200). |

## issue-local

Body:

```json
{"Cuit": 30575099943, "PtoVta": 98, "CbteTipo": 6, "ClientRef": "pos1-000123",
 "CycleId": null,
 "FeCAEARegInfReq": {"FeCabReq": {}, "FeDetReq": {"FECAEADetRequest": [{"CbteFch": "20261024", "...": "ARCA fields"}]}}}
```

- Exactly one `FECAEADetRequest` item with `CbteFch` = `YYYYMMDD`. AFRelay sets
  `FeCabReq.PtoVta/CbteTipo` from the request, `CantReg=1`, `CbteDesde=CbteHasta=<number>`
  and `CAEA`; whatever the client sent there is overwritten.
- The cycle is the active one whose `fch_vig_desde..fch_vig_hasta` contains `CbteFch`.
  `CycleId` (optional) forces a cycle; it is **not** checked against `CbteFch`.
- Numbering per (CUIT, PV, type): last local number + 1; with no local voucher, the
  number seeded from ARCA's last authorized (`caea_numbering`, refreshed by PUT ptos-venta
  and every 6 h bootstrap for the types in `CAEA_CBTE_TIPOS`, default `1,3,6,8`); only if
  never seeded, a live ARCA call. **Register the PVs while online** so the first
  contingency voucher works with ARCA down.
- `200` response: `status: "queued"`, `reserved_cbte_nro`, `caea`, `fch_vig_hasta`,
  `fch_tope_inf`, `invoice` (row without the stored request), `job` (the inform job).

### ClientRef (idempotency)

Optional, 1..100 chars, unique per CUIT. Send a value that identifies the sale on the
POS (e.g. POS id + local ticket id) and reuse it on every retry of the same sale. A
repeated `(Cuit, ClientRef)` returns the original invoice (same number, same shape,
`200`) and creates nothing. The same ClientRef with another `PtoVta`/`CbteTipo` is `409`.
Without ClientRef every call issues a new number.

### Status codes

| Code | Meaning |
|---|---|
| `200` | Issued (or ClientRef replay). |
| `404` | No CAEA cycle for this CUIT and `CbteFch` (or `CycleId` of another CUIT). |
| `409` | Cycle chosen by `CycleId` has no CAEA yet; or ClientRef reused for another PV/type. |
| `422` | Malformed body: missing/empty `FECAEADetRequest`, more than one item, missing or non-`YYYYMMDD` `CbteFch`; or a bad `updated_since`. |
| `503` | No local/seeded numbering and ARCA (or the WSAA token file) is unavailable or answered with `Errors`. Short message; retry later with the same ClientRef. |

## Invoice state machine

```
issued_local --(ARCA Resultado A/O)--> informed   (terminal)
issued_local --(ARCA Resultado R)----> rejected   (terminal)
issued_local --(inform job dead)-----> error      (only non-recoverable paths; a manual
                                                   /retry revives it back to issued_local)
```

- While the inform is pending or retrying the invoice stays `issued_local`;
  `last_error` holds the last transient error (network, token, ARCA reply without
  `Resultado`). Inform jobs retry forever with exponential backoff capped at 1 h.
- `informed` and `rejected` never change again, even if ARCA later answers differently.
- For `informed`, `last_error` may hold ARCA observations (`Obs`), not an error.
- `response` is ARCA's reply to the inform (`FECAEADetResponse[0]` decides; CantReg is 1).

## Cursors on GET invoices

- `since_id` alone: `id > since_id ORDER BY id` -- only new invoices. Pass the last `id`.
- `updated_since` (+ `since_id` as tie-break): rows with `updated_at > updated_since`, or
  `updated_at == updated_since AND id > since_id`, `ORDER BY updated_at, id`. Every status
  change bumps `updated_at`, so this is the cursor to follow state changes: pass back the
  last item's `updated_at` and `id`. Start with `updated_since=1970-01-01T00:00:00+00:00`.

## Formats

- `*_at` fields (`created_at`, `updated_at`, `informed_at`, `sin_movimiento_at`): UTC
  ISO 8601 with offset and microseconds, e.g. `2026-10-24T13:05:00.123456+00:00`.
  `updated_since` accepts any ISO 8601 with offset or `Z` (naive = UTC).
- ARCA dates (`CbteFch`, `fch_vig_desde`, `fch_vig_hasta`, `fch_tope_inf`): `YYYYMMDD`,
  Argentina local date. `fch_tope_inf` may be `null` for cycles loaded before AFRelay
  stored it (validity dates are then derived: orden 1 = days 1-15, orden 2 = 16-end).
