"""PHASE 12 — the canonical return lifecycle.

WHAT WAS THERE BEFORE
---------------------
`ReturnStatusUpdate.status` was typed `str` with no validation, and the
endpoint wrote it straight to the database. Verified against the running API:

    PATCH /returns/{id}/status  {"status": "banana"}    -> 200 OK
    PATCH /returns/{id}/status  {"status": "refunded"}  -> 200 OK
    PATCH /returns/{id}/status  {"status": "pending"}   -> 200 OK

The last two in sequence are the real problem. A return that has been refunded
-- money has left the merchant's account -- silently reverts to pending, and
can then be approved and refunded again. Nothing in the system objects.

Free-text status also quietly breaks everything downstream. Reports group by
status, workflow rules match on it, and the dashboard counts it. One typo in
one integration produces a status nobody queries, and returns in it simply
vanish from every view while still existing in the database.

WHY A TABLE, NOT `if` STATEMENTS
--------------------------------
The transition map is data. That means the whole lifecycle can be read in one
place, rendered as a diagram, and tested exhaustively -- every pair of states
is checked in the tests below, not just the paths someone remembered to write.
"""
from __future__ import annotations

from typing import Final

__all__ = [
    "ReturnStatus",
    "TERMINAL_STATUSES",
    "TRANSITIONS",
    "InvalidTransition",
    "can_transition",
    "validate_transition",
    "next_statuses",
]


class InvalidTransition(ValueError):
    """Raised when a status change is not permitted by the lifecycle."""


class ReturnStatus:
    """The canonical set. Anything not here is not a return status."""

    # Intake
    PENDING: Final = "pending"                     # created, not yet scored
    PREDICTION_DONE: Final = "prediction_done"     # scored, awaiting a decision
    UNDER_REVIEW: Final = "under_review"           # a human is looking at it

    # Decision
    APPROVED: Final = "approved"
    REJECTED: Final = "rejected"

    # Reverse logistics
    PICKUP_SCHEDULED: Final = "pickup_scheduled"
    IN_TRANSIT: Final = "in_transit"
    RECEIVED: Final = "received"
    INSPECTION: Final = "inspection"

    # Resolution
    REFUNDED: Final = "refunded"
    CLOSED: Final = "closed"
    CANCELLED: Final = "cancelled"                 # withdrawn before resolution

    # Administrative
    DELETED: Final = "deleted"                     # soft delete


S = ReturnStatus

# Terminal states have no outbound transitions. Reopening is a deliberate,
# audited action (see `reopen`), not an ordinary status change -- which is
# precisely the distinction the old free-text field could not express.
TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({
    S.CLOSED, S.CANCELLED, S.DELETED,
})

TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    S.PENDING: frozenset({
        S.PREDICTION_DONE, S.UNDER_REVIEW, S.APPROVED, S.REJECTED,
        S.CANCELLED, S.DELETED,
    }),
    # Scoring produces a recommendation, not a decision. It can be auto-applied
    # (approved/rejected) or escalated to a human.
    S.PREDICTION_DONE: frozenset({
        S.UNDER_REVIEW, S.APPROVED, S.REJECTED, S.CANCELLED, S.DELETED,
    }),
    S.UNDER_REVIEW: frozenset({
        S.APPROVED, S.REJECTED, S.CANCELLED, S.DELETED,
    }),
    S.APPROVED: frozenset({
        S.PICKUP_SCHEDULED, S.CANCELLED, S.DELETED,
        # Approved-then-refunded without physical return: "refund and keep",
        # a real disposition for low-value items where reverse shipping costs
        # more than the goods are worth.
        S.REFUNDED,
    }),
    # A rejection can be appealed back into review. Customers dispute
    # decisions, and support staff need a path that is not "create a new
    # return and lose the history".
    S.REJECTED: frozenset({S.UNDER_REVIEW, S.CLOSED, S.DELETED}),

    S.PICKUP_SCHEDULED: frozenset({S.IN_TRANSIT, S.CANCELLED, S.DELETED}),
    S.IN_TRANSIT: frozenset({
        S.RECEIVED, S.DELETED,
        # Couriers lose parcels. That resolves as a refund on the merchant's
        # liability rather than an inspection that will never happen.
        S.REFUNDED,
    }),
    S.RECEIVED: frozenset({S.INSPECTION, S.DELETED}),
    S.INSPECTION: frozenset({S.REFUNDED, S.REJECTED, S.CLOSED, S.DELETED}),
    S.REFUNDED: frozenset({S.CLOSED, S.DELETED}),

    # Terminal.
    S.CLOSED: frozenset(),
    S.CANCELLED: frozenset(),
    S.DELETED: frozenset(),
}

ALL_STATUSES: Final[frozenset[str]] = frozenset(TRANSITIONS)


def can_transition(current: str, target: str) -> bool:
    """Is this status change permitted?

    Unknown current statuses return False rather than raising. Rows predating
    this phase may hold arbitrary strings -- "banana" was demonstrably
    storable -- and those need to fail closed, not crash a page that lists
    them.
    """
    return target in TRANSITIONS.get(current, frozenset())


def validate_transition(current: str, target: str) -> None:
    """Raise InvalidTransition with an explanation, or return silently.

    The messages name what is actually allowed. A bare "invalid transition"
    forces whoever hit it to go read the source, and the person hitting it is
    often an integration partner who cannot.
    """
    if target not in ALL_STATUSES:
        raise InvalidTransition(
            f"{target!r} is not a return status. "
            f"Valid statuses: {', '.join(sorted(ALL_STATUSES))}"
        )

    if current not in ALL_STATUSES:
        raise InvalidTransition(
            f"This return has an unrecognised status ({current!r}), so it "
            f"cannot be transitioned. It predates the lifecycle rules and "
            f"needs to be corrected by an administrator."
        )

    if current == target:
        raise InvalidTransition(
            f"This return is already {current!r}."
        )

    if current in TERMINAL_STATUSES:
        raise InvalidTransition(
            f"This return is {current!r}, which is final. Reopening is a "
            f"separate, audited action -- it is not an ordinary status change."
        )

    if not can_transition(current, target):
        allowed = sorted(TRANSITIONS[current])
        raise InvalidTransition(
            f"A return that is {current!r} cannot become {target!r}. "
            f"From {current!r} it can only become: {', '.join(allowed)}."
        )


def next_statuses(current: str) -> list[str]:
    """What this return can become next. Drives UI: showing a warehouse
    manager only the buttons that will work beats showing them all and
    rejecting half."""
    return sorted(TRANSITIONS.get(current, frozenset()))


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES
