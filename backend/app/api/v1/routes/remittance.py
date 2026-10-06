"""
Courier Remittance Reconciliation.

Sellers get remittance reports from couriers (usually CSV exports from
the courier's own portal) and need to know: did the courier actually pay
what they were supposed to, per order? This exposes two ways to feed that
data in (a JSON endpoint for programmatic use, a CSV upload for the
reports couriers actually hand sellers), plus summary/drill-down views.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.permissions import Permission
from app.api.v1.deps import get_current_org, require_permission
from app.db import store
from app.schemas.schemas import RemittanceIngestRequest, RemittanceIngestResponse
from app.services import remittance_service

router = APIRouter(prefix="/api/v1/remittance", tags=["remittance"])

# PHASE 6: was require_role("org_admin", "finance"). `finance` is not an
# assignable role. Reconciliation moves money, so it stays org_admin-only --
# but now that restriction is stated deliberately rather than by accident.
_can_reconcile = require_permission(Permission.REMITTANCE_RECONCILE)

_ALLOWED_CSV_TYPES = {"text/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB, same limit as document uploads elsewhere in this codebase
_REQUIRED_CSV_COLUMNS = {"platform_order_id", "courier", "remitted_amount", "remittance_date"}


@router.post("/ingest", response_model=RemittanceIngestResponse)
async def ingest_remittance(
    payload: RemittanceIngestRequest,
    org: dict = Depends(get_current_org),
    user: dict = Depends(_can_reconcile),
) -> RemittanceIngestResponse:
    """Reconcile a batch of remittance lines submitted as JSON."""
    lines = [line.model_dump() for line in payload.lines]
    result = remittance_service.reconcile_batch(org["id"], lines)
    return RemittanceIngestResponse(**result)


@router.post("/upload", response_model=RemittanceIngestResponse, status_code=201)
async def upload_remittance_csv(
    file: UploadFile = File(...),
    org: dict = Depends(get_current_org),
    user: dict = Depends(_can_reconcile),
) -> RemittanceIngestResponse:
    """
    Upload a courier's remittance report as a CSV. Expected columns:
    platform_order_id, courier, remitted_amount, remittance_date
    (YYYY-MM-DD), and optionally awb_number.
    """
    if file.content_type not in _ALLOWED_CSV_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed. Upload a CSV file.",
        )

    # Same streamed-read-with-size-check pattern used for document uploads
    # elsewhere in this codebase -- don't buffer an unbounded body in memory.
    chunks = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > _MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File exceeds 10MB limit")
        chunks.append(chunk)
    contents = b"".join(chunks)

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not _REQUIRED_CSV_COLUMNS.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must include columns: {', '.join(sorted(_REQUIRED_CSV_COLUMNS))}",
        )

    lines = []
    for i, row in enumerate(reader, start=2):  # start=2: row 1 is the header
        try:
            lines.append({
                "platform_order_id": row["platform_order_id"].strip(),
                "courier": row["courier"].strip(),
                # The courier's CSV is the origin of every reconciliation
                # figure. float() here would lose precision before the data
                # even entered the system, so the raw string is carried
                # through and converted once, exactly, downstream.
                "remitted_amount": {
                    "amount": row["remitted_amount"].strip().replace(",", ""),
                    "currency": (row.get("currency") or "INR").strip().upper(),
                },
                "remittance_date": row["remittance_date"].strip(),
                "awb_number": (row.get("awb_number") or "").strip() or None,
            })
        except (ValueError, KeyError, AttributeError) as exc:
            raise HTTPException(status_code=400, detail=f"Row {i} is malformed: {exc}")

    if not lines:
        raise HTTPException(status_code=400, detail="CSV contained no data rows")

    result = remittance_service.reconcile_batch(org["id"], lines)
    return RemittanceIngestResponse(**result)


@router.get("/summary")
async def remittance_summary(
    org: dict = Depends(get_current_org),
    user: dict = Depends(_can_reconcile),
) -> dict:
    """Totals and per-courier breakdown of expected vs. remitted amounts."""
    return remittance_service.get_summary(org["id"])


@router.get("/mismatches")
async def list_mismatches(
    courier: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    org: dict = Depends(get_current_org),
    user: dict = Depends(_can_reconcile),
) -> list[dict]:
    """Flagged discrepancies, most recent first -- for drill-down."""
    return store.get_remittances_for_org(org["id"], status="mismatch", courier=courier, limit=limit)


@router.get("/unmatched")
async def list_unmatched(
    courier: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    org: dict = Depends(get_current_org),
    user: dict = Depends(_can_reconcile),
) -> list[dict]:
    """Remittance lines with no matching pre-shipment assessment on file."""
    return store.get_remittances_for_org(org["id"], status="unmatched_no_expected", courier=courier, limit=limit)
