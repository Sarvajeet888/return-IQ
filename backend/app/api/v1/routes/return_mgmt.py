"""
Extended Return Management (Phase 5.3) + File & Document Management (Phase 5.8)
Covers: return timeline/notes, document upload, bulk import, delete return.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import magic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.money import Money
from app.api.v1.deps import get_current_org, get_current_user, require_permission
from app.core.permissions import Permission
from app.db import store
from app.services import (
    audit_service,
    evidence_service,
    feature_engineering,
    image_service,
    signal_agreement,
)
from app.services import storage_service
from app.schemas.schemas import BulkReturnImport, ReturnNoteAdd
from app.services.feature_mapping import build_feature_dict
from app.services.ml_service import score_return

router = APIRouter(tags=["return-management"])

_ALLOWED_FILE_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "application/pdf",
}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _get_owned_return_or_404(return_id: str, org: dict) -> dict:
    r = store.get_return_by_id(return_id)
    if not r or (r.get("org_id") != org["id"] and r.get("merchant_id") != org["id"]):
        raise HTTPException(status_code=404, detail="Return not found")
    return r


# ── Return Notes (timeline) ───────────────────────────────────────────────────

def _parse_created_at(value) -> datetime:
    """Point-in-time cutoff for signal analysis.

    Falls back to now() if the timestamp is unreadable — which over-includes
    history rather than under-including it. That direction is the safe one for
    a *review aid*: a reviewer seeing extra context can discount it, whereas
    missing context they needed is invisible to them.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        text = str(value).replace("Z", "").replace(" ", "T", 1)
        return datetime.fromisoformat(text.split("+")[0])
    except (ValueError, TypeError):
        return datetime.now(UTC).replace(tzinfo=None)


def _item_money(ret) -> Money:
    """Inbound item value -> exact Money. Single conversion point for imports."""
    return Money.from_major(ret.item_value, ret.currency)


@router.post("/api/v1/returns/{return_id}/notes", status_code=201)
async def add_note(
    return_id: str,
    payload: ReturnNoteAdd,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    """Add a note to the return timeline."""
    _get_owned_return_or_404(return_id, org)
    note = store.add_return_note({
        "id": str(uuid.uuid4()),
        "return_request_id": return_id,
        "user_id": user["id"],
        "note": payload.note,
        "created_at": datetime.now(UTC),
    })
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "add_note", "detail": f"Note added to return {return_id}",
    })
    return note


@router.get("/api/v1/returns/{return_id}/notes")
async def get_notes(
    return_id: str,
    org: dict = Depends(get_current_org),
) -> list:
    """Get the full timeline of notes for a return."""
    _get_owned_return_or_404(return_id, org)
    return store.get_return_notes(return_id, org["id"])


@router.get("/api/v1/returns/{return_id}/timeline")
async def get_timeline(
    return_id: str,
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Full return timeline: audit log events + notes + SLA status.
    Useful for displaying a chronological view of everything that
    happened to a return in the UI.
    """
    r = _get_owned_return_or_404(return_id, org)
    notes = store.get_return_notes(return_id, org["id"])
    docs = store.get_return_documents(return_id, org["id"])
    sla = store.get_sla_for_return(return_id, org["id"])
    pred = store.get_prediction(return_id, org["id"])

    # Build unified timeline events
    events = []
    events.append({
        "event": "created",
        "ts": r.get("created_at"),
        "detail": f"Return created for order {r.get('platform_order_id')}",
    })
    if pred:
        events.append({
            "event": "prediction_complete",
            "ts": pred.get("created_at"),
            "detail": f"AI scored: routing={pred.get('routing_decision')}, "
                      f"risk={pred.get('risk_score', 0):.0f}, "
                      f"cost={Money(int(pred.get('predicted_cost_minor') or 0), pred.get('currency') or 'INR').format()}",
        })
    for note in notes:
        events.append({
            "event": "note",
            "ts": note.get("created_at"),
            "detail": note.get("note"),
            "user_id": note.get("user_id"),
        })
    for doc in docs:
        events.append({
            "event": "document_uploaded",
            "ts": doc.get("created_at"),
            "detail": f"Document uploaded: {doc.get('file_name')}",
        })
    events.sort(key=lambda e: e.get("ts") or "")

    # PHASE 23 — cross-signal contradictions.
    #
    # Computed from data already held rather than from a model. A fraud score
    # tells a reviewer to look; these tell them what to look at, and each is
    # checkable in seconds.
    #
    # Point-in-time correctness matters here as much as in training: history
    # is evaluated as of this return's creation, so a reviewer opening a
    # six-month-old return sees what was knowable then, not what the customer
    # did afterwards.
    as_of = _parse_created_at(r.get("created_at"))
    customer_history = store.get_returns_for_customer(
        r.get("customer_identifier", ""), org["id"],
    )
    sku_history = store.get_returns_for_sku(r.get("sku", ""), org["id"])

    signals = signal_agreement.analyse_signals(
        r,
        evidence=docs,
        customer_features=feature_engineering.customer_features(
            [h for h in customer_history if h.get("id") != return_id],
            customer_orders_count=0,
            as_of=as_of,
        ),
        product_features=feature_engineering.product_features(
            [h for h in sku_history if h.get("id") != return_id], as_of=as_of,
        ),
    ).as_dict()

    return {
        "return": r,
        "prediction": pred,
        "sla": sla,
        "timeline": events,
        "documents": docs,
        "signal_findings": signals,
    }


# ── Document Upload (5.8) ─────────────────────────────────────────────────────

@router.post("/api/v1/returns/{return_id}/documents", status_code=201)
async def upload_document(
    return_id: str,
    file: UploadFile = File(...),
    is_damage_photo: bool = Form(default=False),
    source: str = Form(default="merchant"),
    evidence_type: str | None = Form(default=None),
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Upload a document (damage photo, invoice, warranty, shipping label) to
    a return. Files are stored as local paths in this implementation —
    replace storage_key logic with S3 when Phase 5.13 (AWS S3) lands.
    """
    # Guard: raises 404 if the return does not belong to this org.
    _get_owned_return_or_404(return_id, org)

    if file.content_type not in _ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed. Allowed: {', '.join(_ALLOWED_FILE_TYPES)}"
        )

    # Stream-read with the size limit enforced DURING the read, not after.
    # Previously `contents = await file.read()` pulled the entire body into
    # memory before checking its length - a client could send an arbitrarily
    # large file and exhaust server memory before the 10MB check ever fired.
    chunks = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > _MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File exceeds 10MB limit")
        chunks.append(chunk)
    contents = b"".join(chunks)

    # Verify the file's ACTUAL content, not just the client-supplied
    # Content-Type header, which is trivially spoofable (e.g. renaming a
    # .exe to photo.png and setting Content-Type: image/png would have
    # sailed through the old check). python-magic reads the real file
    # signature (magic bytes).
    detected_type = magic.from_buffer(contents, mime=True)
    if detected_type not in _ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match an allowed type (detected: {detected_type})."
        )

    # In production: upload to S3, get back a key. Here: simulate a key.
    # Storage filename is now a fresh UUID, not the client-supplied
    # filename - the original name is kept only in `file_name` for display,
    # never used to build a path. Untrusted filenames in a storage path are
    # a path-traversal / overwrite risk the moment this is wired to real
    # storage (e.g. "../../other_org/secret.pdf").
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}.get(detected_type, "")
    storage_key = f"uploads/{org['id']}/{return_id}/{uuid.uuid4()}{ext}"

    # Actually persist the bytes. Previously the key was recorded in the
    # database but the file itself was never written anywhere (KI-011) - the
    # DB referenced a document that did not exist. Routes through
    # storage_service: S3 when AWS_S3_BUCKET is set, local disk otherwise.
    if not storage_service.store_file(storage_key, contents, detected_type):
        raise HTTPException(
            status_code=500,
            detail="Could not store the uploaded file. Please try again.",
        )

    # PHASE 22 — strip identifying metadata before anything else touches the
    # bytes. A phone photograph of a damaged shirt carries the customer's GPS
    # coordinates, device model and original timestamp; storing it verbatim
    # puts their home address in the merchant's object storage. Under DPDP
    # that is personal data collected with no purpose and no consent.
    image_meta: dict | None = None
    if detected_type.startswith("image/"):
        try:
            processed = image_service.process_evidence_image(contents)
        except image_service.ImageProcessingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # The stored bytes are the cleaned bytes. The hash below is therefore
        # of what we actually keep, not of what arrived -- which is the
        # correct thing to hash, since the integrity claim is about the file
        # in storage.
        contents = processed.content
        image_meta = processed.as_dict()

    # PHASE 13 — provenance and integrity.
    file_hash = evidence_service.content_hash(contents)

    try:
        evidence_source = evidence_service.validate_source(source)
        # Backward compatibility: the old API had only `is_damage_photo`.
        # Honour it when no explicit type is given, so existing integrations
        # keep working and still land in the right taxonomy bucket.
        resolved_type = evidence_type or (
            evidence_service.EvidenceType.DAMAGE_PHOTO if is_damage_photo else None
        )
        evidence_kind = evidence_service.validate_type(resolved_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Has this exact file been submitted on another return? Advisory only --
    # a fact for a human to weigh, not grounds to reject the upload.
    reuse = evidence_service.check_reuse(
        store.get_documents_by_hash(org["id"], file_hash),
        file_hash,
        return_id,
    )

    doc = store.store_return_document({
        "id": str(uuid.uuid4()),
        "return_request_id": return_id,
        "org_id": org["id"],
        "uploaded_by_user_id": user["id"],
        "file_name": file.filename,
        # PHASE 13 fix: persist the VERIFIED type from magic-byte inspection,
        # not file.content_type. The client's header is what an attacker
        # controls; storing it meant the database recorded an unverified claim
        # while the object store held the verified one. Both currently pass
        # the same allow-list, so this was not exploitable -- but a value
        # nobody verified should not be the one we keep.
        "file_type": detected_type,
        "declared_file_type": file.content_type,
        "file_size_bytes": len(contents),
        "storage_key": storage_key,
        "is_damage_photo": is_damage_photo,
        "content_sha256": file_hash,
        "source": evidence_source,
        "evidence_type": evidence_kind,
        "created_at": datetime.now(UTC),
    })

    audit_service.record(
        org_id=org["id"],
        user_id=user["id"],
        action="evidence_uploaded",
        resource_type="return",
        resource_id=return_id,
        detail=f"{evidence_kind} from {evidence_source}: {file.filename}",
        changes={"sha256": file_hash, "reused": reuse["reused"]},
    )

    if reuse["reused"]:
        doc = {**doc, "reuse_warning": reuse}
    if image_meta:
        doc = {**doc, "image_processing": image_meta}
    return doc


@router.get("/api/v1/returns/{return_id}/documents")
async def list_documents(
    return_id: str,
    org: dict = Depends(get_current_org),
) -> list:
    _get_owned_return_or_404(return_id, org)
    return store.get_return_documents(return_id, org["id"])


@router.delete("/api/v1/returns/{return_id}/documents/{doc_id}")
async def delete_document(
    return_id: str,
    doc_id: str,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    _get_owned_return_or_404(return_id, org)
    deleted = store.delete_return_document(doc_id, org["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "delete_document", "detail": f"Deleted document {doc_id}",
    })
    return {"message": "Document deleted"}


# ── Delete Return ─────────────────────────────────────────────────────────────

@router.delete("/api/v1/returns/{return_id}")
async def delete_return(
    return_id: str,
    user: dict = Depends(require_permission(Permission.RETURNS_DELETE)),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Soft-delete a return by setting status to 'deleted'.
    Hard-delete is not provided — retain data for audit trail and future ML training.
    Only org_admin+ can delete.
    """
    _get_owned_return_or_404(return_id, org)
    store.store_return({"id": return_id, "status": "deleted"})
    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "delete_return", "detail": f"Return {return_id} soft-deleted",
    })
    return {"message": "Return deleted"}


# ── Bulk Import ───────────────────────────────────────────────────────────────

@router.post("/api/v1/returns/bulk", status_code=201)
async def bulk_import_returns(
    payload: BulkReturnImport,
    user: dict = Depends(get_current_user),
    org: dict = Depends(get_current_org),
) -> dict:
    """
    Submit multiple returns in one request. Useful for migrating historical
    data or batch-processing end-of-day returns from an ERP.

    Returns are scored individually. On partial failure, successfully
    scored returns are still saved — the response lists which IDs failed
    and why, rather than rolling back everything.
    """
    if len(payload.returns) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 returns per bulk import")

    successes = []
    failures = []

    for i, ret in enumerate(payload.returns):
        try:
            return_id = str(uuid.uuid4())
            now = datetime.now(UTC)
            return_data = {
                "id": return_id,
                "org_id": org["id"],
                "merchant_id": org["id"],
                "platform_order_id": ret.platform_order_id,
                "customer_identifier": ret.customer_identifier,
                "sku": ret.sku,
                "item_category": ret.item_category,
                # `ret` is the inbound ReturnRequestCreate, so item_value is a
                # Decimal in major units. Convert once, here at the boundary.
                "item_value_minor": _item_money(ret).minor_units,
                "currency": ret.currency,
                "origin_pincode": ret.origin_pincode,
                "destination_pincode": ret.destination_pincode,
                "weight_grams": ret.weight_grams,
                "volumetric_weight_grams": ret.volumetric_weight_grams,
                "return_reason_code": ret.return_reason_code,
                "courier": ret.courier,
                "payment_mode": ret.payment_mode,
                "fragile": ret.fragile,
                "festive": ret.festive,
                "condition": ret.condition or "good",
                "customer_notes": ret.customer_notes,
                "raw_payload": ret.raw_payload,
                "status": "pending",
                "created_at": now,
            }
            customer_count = store.count_customer_returns(ret.customer_identifier, org["id"])
            org_count = store.count_org_returns(org["id"])
            features = build_feature_dict(return_data, customer_count, org_count)
            result = score_return(
                features=features,
                item_value=float(ret.item_value),  # ml heuristics score in major units
                risk_threshold=float(org.get("risk_threshold", 50.0)),
                condition=ret.condition,
            )
            return_data["status"] = "prediction_done"
            store.store_return(return_data)
            pred_data = {
                "id": str(uuid.uuid4()),
                "return_request_id": return_id,
                "predicted_cost_minor": Money.from_major(result["predicted_cost_inr"], ret.currency).minor_units,
                "currency": ret.currency,
                "risk_score": float(result["risk_score"]),
                "fraud_score": float(result["fraud_score"]),
                "damage_probability": result["damage_probability"],
                "resale_value_estimate_minor": Money.from_major(result["resale_value_estimate"], ret.currency).minor_units,
                "carbon_footprint_kg": result["carbon_footprint_kg"],
                "confidence_score": result["confidence_score"],
                "routing_decision": result["routing_decision"].value,
                "model_version": result["model_version"],
                "inference_latency_ms": result["inference_latency_ms"],
                "feature_snapshot": result["feature_snapshot"],
                "explainability": result["explainability"],
                "created_at": now,
            }
            store.store_prediction(pred_data)
            successes.append({"index": i, "return_id": return_id, "order_id": ret.platform_order_id})
        except Exception as exc:
            failures.append({"index": i, "order_id": ret.platform_order_id, "error": str(exc)})

    store.add_audit_log({
        "org_id": org["id"], "user_id": user["id"],
        "action": "bulk_import",
        "detail": f"Bulk import: {len(successes)} success, {len(failures)} failed",
    })
    return {
        "imported": len(successes),
        "failed": len(failures),
        "successes": successes,
        "failures": failures,
    }
