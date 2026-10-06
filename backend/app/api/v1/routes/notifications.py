"""
Notifications & Communication (Phase 5.7)
In-app notifications with mark-read, unread counts, and severity filtering.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_org
from app.db import store
from app.schemas.schemas import NotificationMarkRead

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/")
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    severity: str | None = None,
    org: dict = Depends(get_current_org),
) -> dict:
    """
    List notifications with optional filtering. Returns count of unread
    alongside items so the UI badge can be updated in one request.
    """
    notifications = store.get_notifications_for_org(org["id"], limit=limit)
    if unread_only:
        notifications = [n for n in notifications if not n.get("read")]
    if severity:
        notifications = [n for n in notifications if n.get("severity") == severity]
    unread_count = store.get_unread_notification_count(org["id"])
    return {
        "items": notifications,
        "total": len(notifications),
        "unread_count": unread_count,
    }


@router.get("/unread-count")
async def unread_count(org: dict = Depends(get_current_org)) -> dict:
    return {"unread_count": store.get_unread_notification_count(org["id"])}


@router.post("/mark-read")
async def mark_read(
    payload: NotificationMarkRead,
    org: dict = Depends(get_current_org),
) -> dict:
    """Mark specific notifications as read."""
    count = store.mark_notifications_read(org["id"], payload.notification_ids)
    return {"marked_read": count}


@router.post("/mark-all-read")
async def mark_all_read(org: dict = Depends(get_current_org)) -> dict:
    """Mark all notifications as read."""
    all_notifs = store.get_notifications_for_org(org["id"], limit=1000)
    ids = [n["id"] for n in all_notifs if not n.get("read")]
    if ids:
        store.mark_notifications_read(org["id"], ids)
    return {"marked_read": len(ids)}
