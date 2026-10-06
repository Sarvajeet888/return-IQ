"""PHASE 13 — return evidence.

WHY HASH THE CONTENT
--------------------
Evidence is the factual basis for a decision that moves money, and in a
chargeback dispute it is what the merchant produces. "The customer sent us
this photo" is an assertion unless you can show the stored bytes are the
uploaded bytes. A SHA-256 of the content makes that demonstrable: substitute
the file in object storage and the hash no longer matches.

THE SECOND USE, WHICH MATTERS MORE COMMERCIALLY
-----------------------------------------------
The same hash detects *reuse*. A customer who submits the identical damage
photograph across several returns is not unlucky — they are photographing one
broken item once and claiming against it repeatedly. This is one of the most
common retail return frauds, and it is invisible to a fraud model trained on
order attributes, because every individual order looks ordinary.

Worth being precise about the limits: this catches byte-identical files. Any
re-encode, crop, or single-pixel edit produces a different hash. Perceptual
hashing (pHash/dHash) catches visually-similar images and is the right next
step -- logged for Phase 22 rather than implied here. Exact-match is still
worth having: it costs one hash computation, and people committing this fraud
usually attach the same file.

WHAT THIS IS NOT
----------------
Not proof the photograph depicts what it claims to. It proves the file has not
changed since upload, and that this exact file has (or has not) been seen
before. Whether the item is genuinely damaged is Phase 22.
"""
from __future__ import annotations

import hashlib
from typing import Any, Final

__all__ = [
    "EvidenceSource",
    "EvidenceType",
    "content_hash",
    "check_reuse",
]


class EvidenceSource:
    """Who produced this evidence.

    A damage photo from the customer and one from the receiving bay are
    different kinds of claim: the first is what is being alleged, the second
    is what was observed. A fraud analyst comparing them needs to know which
    is which, and the previous schema had no way to say.
    """

    CUSTOMER: Final = "customer"        # uploaded via the return portal
    MERCHANT: Final = "merchant"        # merchant staff, general
    WAREHOUSE: Final = "warehouse"      # receiving bay, on arrival
    INSPECTOR: Final = "inspector"      # formal inspection step
    COURIER: Final = "courier"          # proof of pickup/delivery
    SYSTEM: Final = "system"            # generated, e.g. a shipping label


VALID_SOURCES: Final[frozenset[str]] = frozenset({
    EvidenceSource.CUSTOMER, EvidenceSource.MERCHANT, EvidenceSource.WAREHOUSE,
    EvidenceSource.INSPECTOR, EvidenceSource.COURIER, EvidenceSource.SYSTEM,
})


class EvidenceType:
    """What the file is.

    A taxonomy rather than the previous single `is_damage_photo` boolean, so
    Phase 22 can select "customer damage photos" as a training population
    instead of inferring it from filenames.
    """

    DAMAGE_PHOTO: Final = "damage_photo"
    PACKAGING_PHOTO: Final = "packaging_photo"
    PRODUCT_PHOTO: Final = "product_photo"
    INVOICE: Final = "invoice"
    WARRANTY: Final = "warranty"
    SHIPPING_LABEL: Final = "shipping_label"
    INSPECTION_REPORT: Final = "inspection_report"
    OTHER: Final = "other"


VALID_TYPES: Final[frozenset[str]] = frozenset({
    EvidenceType.DAMAGE_PHOTO, EvidenceType.PACKAGING_PHOTO,
    EvidenceType.PRODUCT_PHOTO, EvidenceType.INVOICE, EvidenceType.WARRANTY,
    EvidenceType.SHIPPING_LABEL, EvidenceType.INSPECTION_REPORT,
    EvidenceType.OTHER,
})


def content_hash(content: bytes) -> str:
    """SHA-256 of the file's bytes.

    SHA-256 rather than MD5 deliberately. MD5 collisions are constructible on
    a laptop, which for a *dedup* cache would be a curiosity but here would
    let someone craft a benign image colliding with a flagged one -- or, worse,
    argue in a dispute that the hash proves nothing. If the hash is going to
    be cited as evidence, it needs to be a hash nobody can forge against.
    """
    return hashlib.sha256(content).hexdigest()


def check_reuse(
    existing_documents: list[dict[str, Any]],
    file_hash: str,
    current_return_id: str,
) -> dict[str, Any]:
    """Has this exact file been submitted before, on other returns?

    Returns a structured finding rather than a bare bool, because the same
    hash means different things in different places and the difference is not
    the system's to decide:

    - Same file on the SAME return: benign. A customer re-uploading after a
      failed submission, or attaching the same photo twice. Not reported.
    - Same file on a DIFFERENT return by the SAME customer: the fraud pattern.
    - Same file on a different return by a DIFFERENT customer: usually a stock
      product image, occasionally a shared fraud kit. Reported, weighted lower.

    Deliberately advisory. This surfaces a fact for a human to weigh; it does
    not reject the upload. A customer with two genuinely identical returns --
    same product, same defect, same photo taken once -- exists, and blocking
    them automatically would be a support ticket the merchant cannot answer.
    """
    matches = [
        d for d in existing_documents
        if d.get("content_sha256") == file_hash
        and d.get("return_request_id") != current_return_id
    ]

    if not matches:
        return {"reused": False, "match_count": 0, "matches": []}

    return {
        "reused": True,
        "match_count": len(matches),
        "matches": [
            {
                "document_id": d.get("id"),
                "return_request_id": d.get("return_request_id"),
                "uploaded_at": str(d.get("created_at")),
                "source": d.get("source"),
            }
            for d in matches[:10]      # cap: a finding, not a data dump
        ],
        "note": (
            f"This exact file has already been submitted on {len(matches)} "
            f"other return(s). Identical evidence across separate returns is "
            f"a common pattern in return fraud, though it can also be a stock "
            f"product image. Worth a look before deciding."
        ),
    }


def validate_source(value: str | None) -> str:
    if not value:
        return EvidenceSource.MERCHANT
    v = value.strip().lower()
    if v not in VALID_SOURCES:
        raise ValueError(
            f"{value!r} is not a valid evidence source. "
            f"Valid: {', '.join(sorted(VALID_SOURCES))}"
        )
    return v


def validate_type(value: str | None) -> str:
    if not value:
        return EvidenceType.OTHER
    v = value.strip().lower()
    if v not in VALID_TYPES:
        raise ValueError(
            f"{value!r} is not a valid evidence type. "
            f"Valid: {', '.join(sorted(VALID_TYPES))}"
        )
    return v
