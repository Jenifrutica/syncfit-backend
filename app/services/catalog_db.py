"""Database-backed catalogs.

The packaged JSON is the seed; from then on the database is the source of truth.
Every read in the app goes through `syncfit_contracts` loaders, which the backend
points at these rows with `set_catalog` at startup and after every edit.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from syncfit_contracts import (
    Exercise,
    GymMachine,
    Supplement,
    packaged_catalog,
    set_catalog,
)
from syncfit_database import CatalogItem

KINDS = ("exercise", "machine", "symptom", "supplement")

_MODELS = {"exercise": Exercise, "machine": GymMachine, "supplement": Supplement}


def item_key(kind: str, external_id: str) -> str:
    return f"{kind}:{external_id}"


def _payload(item: object) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")  # type: ignore[union-attr]
    return dict(item)  # type: ignore[arg-type]


def ensure_catalog(session: Session) -> int:
    """Insert the packaged rows that are missing; never overwrite edits."""
    existing = {row_id for (row_id,) in session.query(CatalogItem.id).all()}
    added = 0
    for kind, items in packaged_catalog().items():
        for order, item in enumerate(items):
            data = _payload(item)
            external_id = str(data.get("id") or "")
            if not external_id:
                continue
            key = item_key(kind, external_id)
            if key in existing:
                continue
            session.add(
                CatalogItem(
                    id=key,
                    kind=kind,
                    external_id=external_id,
                    payload=data,
                    sort_order=order,
                )
            )
            added += 1
    session.flush()
    return added


def load_registry(session: Session) -> None:
    """Point the contracts loaders at the active database rows."""
    rows = (
        session.query(CatalogItem)
        .filter(CatalogItem.active.is_(True))
        .order_by(CatalogItem.kind, CatalogItem.sort_order)
        .all()
    )
    buckets: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    for row in rows:
        if row.kind in buckets:
            buckets[row.kind].append(row.payload or {})
    set_catalog(
        exercises=[Exercise.model_validate(payload) for payload in buckets["exercise"]],
        machines=[GymMachine.model_validate(payload) for payload in buckets["machine"]],
        symptoms=list(buckets["symptom"]),
        supplements=[Supplement.model_validate(payload) for payload in buckets["supplement"]],
    )


def validate_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate (and normalize) one catalog row; raises ValueError when invalid."""
    if kind not in KINDS:
        raise ValueError(f"unknown catalog kind: {kind}")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    external_id = str(payload.get("id") or "").strip()
    if not external_id:
        raise ValueError("id is required")
    model = _MODELS.get(kind)
    if model is None:  # symptoms are plain JSON data
        data = dict(payload)
    else:
        data = model.model_validate(payload).model_dump(mode="json")
    data["id"] = external_id
    return data


def list_items(session: Session, kind: str) -> list[CatalogItem]:
    return (
        session.query(CatalogItem)
        .filter(CatalogItem.kind == kind)
        .order_by(CatalogItem.active.desc(), CatalogItem.sort_order, CatalogItem.external_id)
        .all()
    )


def upsert(session: Session, kind: str, payload: dict[str, Any], sort_order: int | None = None) -> CatalogItem:
    """Create or replace one row. The caller commits and reloads the registry."""
    data = validate_payload(kind, payload)
    external_id = data["id"]
    key = item_key(kind, external_id)
    row = session.get(CatalogItem, key)
    if row is None:
        if sort_order is None:
            last = (
                session.query(CatalogItem.sort_order)
                .filter(CatalogItem.kind == kind)
                .order_by(CatalogItem.sort_order.desc())
                .first()
            )
            sort_order = (last[0] + 1) if last else 0
        row = CatalogItem(id=key, kind=kind, external_id=external_id, sort_order=sort_order)
        session.add(row)
    row.payload = data
    row.active = True
    if sort_order is not None:
        row.sort_order = sort_order
    session.flush()
    return row


def set_active(session: Session, kind: str, external_id: str, active: bool) -> CatalogItem | None:
    row = session.get(CatalogItem, item_key(kind, external_id))
    if row is not None:
        row.active = active
        session.flush()
    return row


__all__ = [
    "KINDS",
    "ensure_catalog",
    "item_key",
    "list_items",
    "load_registry",
    "set_active",
    "upsert",
    "validate_payload",
]
