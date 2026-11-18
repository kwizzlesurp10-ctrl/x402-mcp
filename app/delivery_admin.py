"""Operator-only read API for settlement delivery records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app import delivery_store
from app.operator_auth import require_operator

router = APIRouter(tags=["admin"])


@router.get("/admin/deliveries")
def list_settlement_deliveries(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Page durable delivery records newest-first (join key: ``tx``)."""
    require_operator(request)
    return delivery_store.list_deliveries(offset=offset, limit=limit)


@router.get("/admin/deliveries/{tx_hash}")
def get_settlement_delivery(request: Request, tx_hash: str) -> dict:
    require_operator(request)
    rec = delivery_store.get_delivery(tx_hash)
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "tx": tx_hash})
    return rec