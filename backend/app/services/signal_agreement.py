"""PHASE 23 — multimodal signal agreement.

THE INSTRUCTION
---------------
> Customer says: "Screen is cracked."   Image: visible damage.
> Order history: normal.                Shipping: high handling-risk route.
> ReturnIQ combines the signals.

WHAT IS BUILDABLE WITHOUT A VISION MODEL
----------------------------------------
The example above needs a CV model to confirm "visible damage", and that is
blocked. But the *combining* is not, and combining is where the value is.

A single signal is rarely decisive. Every individual fact about a return looks
ordinary: a damage claim is ordinary, a customer with three prior returns is
ordinary, a SKU that occasionally arrives broken is ordinary. What is not
ordinary is a damage claim on a product that has never been damaged for anyone
else, from a customer who claims damage every time.

**Contradictions are computable from data ReturnIQ already holds.** They do
not need a model at all — they need the signals to be checked against each
other rather than each being scored in isolation, which is what the current
system does.

WHY CONTRADICTION RATHER THAN SCORE
-----------------------------------
A fraud score of 68 tells a reviewer to look. It does not tell them what to
look at. "The customer reports the item arrived damaged, but recorded its
condition as good" tells them exactly where to start, and is checkable — the
reviewer can confirm or dismiss it in seconds.

This module produces findings, not verdicts. A contradiction is a question
worth asking, and several have innocent explanations that only a human can
recognise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "Finding",
    "Severity",
    "SignalReport",
    "analyse_signals",
]


class Severity:
    """How much attention a finding deserves.

    Deliberately three levels. More would imply a precision this does not
    have, and a reviewer working a queue needs to know "look now", "look", or
    "noted" — not a 1-10 scale they will have to calibrate themselves.
    """

    STRONG: Final = "strong"        # hard to explain innocently
    MODERATE: Final = "moderate"    # worth checking
    WEAK: Final = "weak"            # context, not evidence


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    signals: list[str]              # which signals disagree
    finding: str                    # what a reviewer should know
    innocent_explanation: str       # the reason this might be nothing

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "signals_involved": self.signals,
            "finding": self.finding,
            "could_also_be": self.innocent_explanation,
        }


@dataclass
class SignalReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def strong(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.STRONG]

    @property
    def needs_review(self) -> bool:
        return bool(self.strong) or len(self.findings) >= 3

    def as_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.as_dict() for f in self.findings],
            "strong_count": len(self.strong),
            "total_count": len(self.findings),
            "needs_review": self.needs_review,
            "note": (
                "These are contradictions between signals, not conclusions. "
                "Each one is a question worth asking — several have innocent "
                "explanations that only a person can recognise."
            ),
        }


_DAMAGE_REASONS: Final[frozenset[str]] = frozenset({
    "damaged", "defective", "broken", "quality_issue",
})


def analyse_signals(
    return_data: dict[str, Any],
    *,
    evidence: list[dict[str, Any]] | None = None,
    customer_features: dict[str, Any] | None = None,
    product_features: dict[str, Any] | None = None,
) -> SignalReport:
    """Check whether the signals about one return agree with each other.

    Every input is optional because real returns arrive incomplete. A missing
    signal produces no finding rather than a finding about the absence —
    inferring guilt from missing data is how a fraud system starts punishing
    customers for the merchant's integration gaps.
    """
    evidence = evidence or []
    customer = customer_features or {}
    product = product_features or {}
    findings: list[Finding] = []

    reason = str(return_data.get("return_reason_code", "")).lower()
    condition = str(return_data.get("condition", "")).lower()
    claims_damage = reason in _DAMAGE_REASONS

    damage_photos = sum(
        1 for d in evidence
        if d.get("evidence_type") == "damage_photo" or d.get("is_damage_photo")
    )

    # ── Text vs structured: the claim contradicts the declared condition ─────
    if claims_damage and condition in {"good", "new", "excellent"}:
        findings.append(Finding(
            code="reason_contradicts_condition",
            severity=Severity.STRONG,
            signals=["return_reason", "declared_condition"],
            finding=(
                f"The return is filed as {reason!r}, but the item's condition "
                f"was recorded as {condition!r}. Those cannot both be right."
            ),
            innocent_explanation=(
                "Condition may have been left at its default by whoever "
                "created the return, rather than actively assessed."
            ),
        ))

    # ── Text vs evidence: a damage claim with no photograph ─────────────────
    if claims_damage and damage_photos == 0:
        findings.append(Finding(
            code="damage_claimed_without_photo",
            severity=Severity.MODERATE,
            signals=["return_reason", "evidence"],
            finding=(
                "Damage is claimed but no damage photograph was submitted."
            ),
            innocent_explanation=(
                "The customer may not have been asked for one, or the return "
                "may have been created by staff on the customer's behalf."
            ),
        ))

    # ── Customer history vs product history: THE multimodal signal ──────────
    #
    # Individually ordinary, jointly not. A customer who reports damage on a
    # product that has never arrived damaged for anyone else is making a claim
    # the product's own history contradicts. Neither signal alone says
    # anything; together they are the single strongest thing this module
    # computes.
    sku_damage_rate = product.get("sku_damage_rate")
    sku_return_count = product.get("sku_return_count", 0)
    customer_returns = customer.get("customer_return_count", 0)

    if (
        claims_damage
        and sku_damage_rate is not None
        and sku_damage_rate < 0.05
        and sku_return_count >= 20          # enough history to mean something
        and customer_returns >= 3
    ):
        findings.append(Finding(
            code="damage_claim_against_product_history",
            severity=Severity.STRONG,
            signals=["return_reason", "product_history", "customer_history"],
            finding=(
                f"This customer reports damage on a product that has arrived "
                f"damaged in only {sku_damage_rate:.0%} of its "
                f"{sku_return_count} other returns. They have returned "
                f"{customer_returns} items previously."
            ),
            innocent_explanation=(
                "Rare events happen, and a single badly-handled parcel is a "
                "real possibility. Check the courier and route before "
                "treating this as a pattern."
            ),
        ))

    # ── Velocity vs claim: burst of returns ─────────────────────────────────
    recent_30d = customer.get("customer_returns_last_30d", 0)
    if recent_30d >= 4:
        findings.append(Finding(
            code="return_velocity_spike",
            severity=Severity.MODERATE if recent_30d < 8 else Severity.STRONG,
            signals=["customer_history", "time"],
            finding=(
                f"{recent_30d} returns from this customer in the last 30 days."
            ),
            innocent_explanation=(
                "Bulk apparel orders are frequently bought in several sizes "
                "with the intention of returning most — normal behaviour that "
                "looks identical to abuse from the outside."
            ),
        ))

    # ── Evidence provenance: who produced it ────────────────────────────────
    #
    # Warehouse and inspector evidence is observed; customer evidence is
    # claimed. A dispute resting entirely on the claimant's own photographs is
    # weaker than one with independent confirmation, and a reviewer should
    # know which they have.
    customer_evidence = sum(1 for d in evidence if d.get("source") == "customer")
    independent_evidence = sum(
        1 for d in evidence
        if d.get("source") in {"warehouse", "inspector", "courier"}
    )
    if claims_damage and customer_evidence > 0 and independent_evidence == 0:
        findings.append(Finding(
            code="no_independent_evidence",
            severity=Severity.WEAK,
            signals=["evidence_provenance"],
            finding=(
                "All evidence for this damage claim came from the customer. "
                "Nothing has been confirmed at the warehouse yet."
            ),
            innocent_explanation=(
                "Entirely normal before the item is received — this is "
                "context, not a concern."
            ),
        ))

    # ── Value vs reason ─────────────────────────────────────────────────────
    item_value_minor = return_data.get("item_value_minor") or 0
    if reason == "change_of_mind" and item_value_minor > 5_000_00:
        findings.append(Finding(
            code="high_value_change_of_mind",
            severity=Severity.MODERATE,
            signals=["return_reason", "item_value"],
            finding=(
                f"A change-of-mind return on an item worth "
                f"Rs {item_value_minor / 100:,.0f}."
            ),
            innocent_explanation=(
                "High-value purchases attract more deliberation, and buyer's "
                "remorse on expensive items is ordinary."
            ),
        ))

    # ── First-time customer, high value, COD ─────────────────────────────────
    if (
        customer.get("customer_is_first_return") is True
        and item_value_minor > 10_000_00
        and str(return_data.get("payment_mode", "")).upper() == "COD"
    ):
        findings.append(Finding(
            code="first_return_high_value_cod",
            severity=Severity.MODERATE,
            signals=["customer_history", "item_value", "payment_mode"],
            finding=(
                "First return from this customer, on a high-value "
                "cash-on-delivery order."
            ),
            innocent_explanation=(
                "Every legitimate customer has a first return, and COD is the "
                "default payment method for much of India. This combination "
                "is common among entirely genuine buyers."
            ),
        ))

    return SignalReport(findings=findings)
