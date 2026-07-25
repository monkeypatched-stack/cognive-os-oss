"""A small, real grocery ordering backend — FastAPI + MongoDB, with API-key
authentication and role-based authorization.

Auth follows the pattern used throughout monkeypatched's API
(src/monkey_brain/api/dependencies.py): a Bearer/X-API-Key credential,
secure by default (GROCERY_AUTH_REQUIRED=true) — a deployment that forgets
to configure auth gets a locked door, not an open one. Persistence follows
monkeypatched's Motor/AsyncIOMotorClient pattern
(src/monkey_brain/persistence/mongodb_adapter.py), wired up via FastAPI's
lifespan context manager the same way src/monkey_brain/api/main.py boots
its own dependencies.

Run:
    export GROCERY_MONGODB_URL=mongodb://localhost:27017   # optional, this is the default
    export GROCERY_DB_NAME=grocery                          # optional, this is the default
    uvicorn examples.grocery_service:app --port 8834

On first boot (empty api_keys collection), three API keys are minted and
logged once — pin them across restarts with GROCERY_ADMIN_API_KEY /
GROCERY_CUSTOMER_API_KEY / GROCERY_RIDER_API_KEY. Only their SHA-256 hash
is ever stored. The seeded customer also gets a starting wallet balance
(GROCERY_STARTING_BALANCE, default 100.0) — orders are real payments:
stock, wallet balance, and a shipment record are all created together in
one multi-document transaction (this deployment's mongod is a replica set,
so transactions are available), so a payment failure can never leave stock
decremented with no money taken, or an order with no shipment.

Shipping lifecycle: every order gets a shipment in "pending" status. An
admin assigns a rider (POST /shipments/{order_id}/assign), which moves it
to "assigned"; only that rider (or an admin) can then advance it through
"out_for_delivery" -> "delivered" (PATCH /shipments/{order_id}/status) —
transitions are validated, no skipping or going backward.

Notifications: every order/shipment status change emails the customer via
n8n's real Gmail-backed workflow (N8N_EMAIL_WEBHOOK_URL, default
http://localhost:5678/webhook/email-notify — the "MonkeyBrain — Email
Notifications" workflow, Webhook -> Gmail -> Respond). A notification
failure never blocks the underlying order/shipment operation — it's logged
and reported back via a `notified` flag, not raised.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

logger = logging.getLogger("grocery_service")

MONGODB_URL = os.getenv("GROCERY_MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("GROCERY_DB_NAME", "grocery")

AUTH_REQUIRED = os.getenv("GROCERY_AUTH_REQUIRED", "true").strip().lower() not in (
    "false", "0", "no", "off",
)

ROLES = {"customer", "rider", "admin"}

N8N_EMAIL_WEBHOOK_URL = os.getenv(
    "N8N_EMAIL_WEBHOOK_URL", "http://localhost:5678/webhook/email-notify",
)

_SEED_CATALOG = [
    {"_id": "milk", "product_id": "prod-milk", "name": "Whole Milk", "unit": "liter", "price_per_unit": 1.20, "stock": 50.0},
    {"_id": "eggs", "product_id": "prod-eggs", "name": "Eggs (dozen)", "unit": "dozen", "price_per_unit": 3.50, "stock": 30.0},
    {"_id": "bread", "product_id": "prod-bread", "name": "Bread", "unit": "loaf", "price_per_unit": 2.75, "stock": 20.0},
]


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


STARTING_BALANCE = float(os.getenv("GROCERY_STARTING_BALANCE", "100.0"))


async def _seed(db: Any) -> None:
    if await db.products.count_documents({}) == 0:
        await db.products.insert_many([dict(p) for p in _SEED_CATALOG])
        logger.info("Seeded product catalog (%d items)", len(_SEED_CATALOG))

    if await db.api_keys.count_documents({}) == 0:
        admin_key = os.getenv("GROCERY_ADMIN_API_KEY") or secrets.token_urlsafe(24)
        customer_key = os.getenv("GROCERY_CUSTOMER_API_KEY") or secrets.token_urlsafe(24)
        rider_key = os.getenv("GROCERY_RIDER_API_KEY") or secrets.token_urlsafe(24)
        await db.api_keys.insert_many([
            {"_id": _hash_key(admin_key), "owner": "admin", "role": "admin"},
            {"_id": _hash_key(customer_key), "owner": "alice", "role": "customer"},
            {"_id": _hash_key(rider_key), "owner": "rider1", "role": "rider"},
        ])
        await db.wallets.insert_many([
            {"_id": "alice", "balance": STARTING_BALANCE},
        ])
        await db.riders.insert_one(
            {"_id": "rider1", "name": "Rider One", "status": "available"},
        )
        await db.customers.insert_one(
            {"_id": "alice", "email": os.getenv("GROCERY_ALICE_EMAIL", "prashunjaveri@gmail.com")},
        )
        logger.warning(
            "Seeded API keys (only SHA-256 hashes are stored) — "
            "ADMIN_API_KEY=%s CUSTOMER_API_KEY=%s RIDER_API_KEY=%s — save "
            "these now. alice's wallet starts at %.2f.",
            admin_key, customer_key, rider_key, STARTING_BALANCE,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    await client.admin.command("ping")  # fail fast if Mongo isn't actually reachable
    await _seed(db)
    app.state.db = db
    app.state.mongo_client = client
    logger.info("Connected to MongoDB %s (db=%s)", MONGODB_URL, DB_NAME)
    yield
    client.close()


app = FastAPI(title="Local Grocery Service", lifespan=lifespan)


class Principal(BaseModel):
    owner: str
    role: str


async def get_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    """Authenticate via `Authorization: Bearer <key>` or `X-API-Key: <key>`.

    Secure by default: a missing/invalid key is rejected unless
    GROCERY_AUTH_REQUIRED is explicitly disabled for local dev.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif x_api_key:
        token = x_api_key

    if not token:
        if AUTH_REQUIRED:
            raise HTTPException(
                status_code=401,
                detail="Missing Authorization: Bearer <key> or X-API-Key header",
            )
        return Principal(owner="anonymous", role="admin")

    record = await request.app.state.db.api_keys.find_one({"_id": _hash_key(token)})
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return Principal(owner=record["owner"], role=record["role"])


def require_role(role: str):
    """Gate an endpoint to a specific role. admin always satisfies any role
    check — customer and rider are lateral (neither is "more" than the
    other), so this is exact-match-or-admin, not a rank comparison.
    """

    async def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role != "admin" and principal.role != role:
            raise HTTPException(status_code=403, detail=f"Role '{role}' required")
        return principal

    return _check


class Address(BaseModel):
    line1: str
    city: str
    postal_code: str


class OrderRequest(BaseModel):
    item: str
    quantity: float
    address: Address


SHIPMENT_TRANSITIONS = {
    "pending": {"assigned"},
    "assigned": {"out_for_delivery"},
    "out_for_delivery": {"delivered"},
    "delivered": set(),
}


@app.get("/products")
async def search_products(
    request: Request, q: str = "", principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    q = q.lower()
    cursor = request.app.state.db.products.find({"_id": {"$regex": q}}, {"_id": 0})
    return {"results": [p async for p in cursor]}


async def _notify(db: Any, owner: str, subject: str, message: str) -> bool:
    """Email the customer via n8n's real Gmail-backed workflow.

    Never raises — a notification failure must not roll back or block the
    order/shipment change it's reporting on. Returns whether it actually
    went out, so callers can surface that honestly instead of assuming.
    """
    customer = await db.customers.find_one({"_id": owner})
    to = customer["email"] if customer else None
    if not to:
        logger.warning("No email on file for %r — notification not sent: %s", owner, subject)
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                N8N_EMAIL_WEBHOOK_URL,
                json={"to": to, "subject": subject, "message": message},
            )
        response.raise_for_status()
        sent = bool(response.json().get("gmail_message_id"))
        if not sent:
            logger.warning("n8n responded but no gmail_message_id — treating as not sent: %s", response.text)
        return sent
    except httpx.HTTPError as exc:
        logger.warning("Notification failed (%s): %s", subject, exc)
        return False


async def _place_order(
    session: Any, db: Any, item: str, quantity: float, owner: str, address: Address,
) -> dict[str, Any]:
    """Runs inside a transaction — either every write below commits, or
    (on any exception, including the HTTPExceptions raised here) none do.
    """
    # Atomic conditional decrement — a stock check followed by a separate
    # write would race under concurrent orders; this update only succeeds
    # if the current stock still covers the request.
    product = await db.products.find_one_and_update(
        {"_id": item, "stock": {"$gte": quantity}},
        {"$inc": {"stock": -quantity}},
        return_document=True, session=session,
    )
    if product is None:
        existing = await db.products.find_one({"_id": item}, session=session)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"product_not_found: {item}")
        raise HTTPException(
            status_code=409,
            detail=f"insufficient_stock: have {existing['stock']}, need {quantity}",
        )

    cost = round(quantity * product["price_per_unit"], 2)

    # Payment — same atomic conditional-decrement pattern as stock, in the
    # same transaction: if this fails, the stock decrement above is rolled
    # back too (session.with_transaction aborts on exception).
    wallet = await db.wallets.find_one_and_update(
        {"_id": owner, "balance": {"$gte": cost}},
        {"$inc": {"balance": -cost}},
        return_document=True, session=session,
    )
    if wallet is None:
        existing_wallet = await db.wallets.find_one({"_id": owner}, session=session)
        have = existing_wallet["balance"] if existing_wallet else 0.0
        raise HTTPException(
            status_code=402,
            detail=f"insufficient_funds: have {have}, need {cost}",
        )

    order_id = str(uuid.uuid4())
    order = {
        "_id": order_id,
        "item": item,
        "quantity": quantity,
        "unit": product["unit"],
        "cost": cost,
        "customer": owner,
        "status": "confirmed",
        # find_one_and_update(..., return_document=True) already returns the
        # document AFTER the $inc (pymongo's ReturnDocument.AFTER == True),
        # so product["stock"] is already post-decrement — subtracting
        # quantity again here double-counted it.
        "remaining_stock": product["stock"],
        "wallet_balance_after": wallet["balance"],
    }
    await db.orders.insert_one(dict(order), session=session)

    # Every paid order gets a shipment — created in the same transaction so
    # a confirmed order can never exist without one.
    shipment = {
        "_id": order_id,
        "order_id": order_id,
        "customer": owner,
        "address": address.model_dump(),
        "status": "pending",
        "rider": None,
    }
    await db.shipments.insert_one(dict(shipment), session=session)

    return order


@app.post("/orders")
async def create_order(
    req: OrderRequest, request: Request, principal: Principal = Depends(require_role("customer")),
) -> dict[str, Any]:
    if req.quantity <= 0:
        raise HTTPException(status_code=422, detail="quantity_must_be_positive")

    db = request.app.state.db
    item = req.item.lower()
    result: dict[str, Any] = {}

    async def _txn(session: Any) -> None:
        result["order"] = await _place_order(
            session, db, item, req.quantity, principal.owner, req.address,
        )

    async with await request.app.state.mongo_client.start_session() as session:
        await session.with_transaction(_txn)

    order = result["order"]
    order["order_id"] = order.pop("_id")
    order["notified"] = await _notify(
        db, principal.owner,
        subject=f"Order confirmed — {order['item']}",
        message=f"Your order for {order['quantity']} {order['unit']} of {order['item']} "
                f"is confirmed. Total charged: {order['cost']}.",
    )
    return order


@app.get("/wallet")
async def get_wallet(
    request: Request, principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    wallet = await request.app.state.db.wallets.find_one({"_id": principal.owner})
    return {"owner": principal.owner, "balance": wallet["balance"] if wallet else 0.0}


@app.get("/orders/{order_id}")
async def get_order(
    order_id: str, request: Request, principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    order = await request.app.state.db.orders.find_one({"_id": order_id})
    if order is None:
        raise HTTPException(status_code=404, detail="order_not_found")
    if principal.role != "admin" and order["customer"] != principal.owner:
        raise HTTPException(status_code=403, detail="not_your_order")
    order["order_id"] = order.pop("_id")
    return order


def _shipment_view(shipment: dict[str, Any]) -> dict[str, Any]:
    shipment = dict(shipment)
    shipment["shipment_id"] = shipment.pop("_id")
    return shipment


async def _get_shipment_or_404(db: Any, order_id: str) -> dict[str, Any]:
    shipment = await db.shipments.find_one({"_id": order_id})
    if shipment is None:
        raise HTTPException(status_code=404, detail="shipment_not_found")
    return shipment


@app.get("/shipments/{order_id}")
async def get_shipment(
    order_id: str, request: Request, principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    shipment = await _get_shipment_or_404(request.app.state.db, order_id)
    is_owner_customer = principal.role == "customer" and shipment["customer"] == principal.owner
    is_assigned_rider = principal.role == "rider" and shipment["rider"] == principal.owner
    if principal.role != "admin" and not is_owner_customer and not is_assigned_rider:
        raise HTTPException(status_code=403, detail="not_your_shipment")
    return _shipment_view(shipment)


class AssignRiderRequest(BaseModel):
    rider_id: str


@app.post("/shipments/{order_id}/assign")
async def assign_rider(
    order_id: str, req: AssignRiderRequest, request: Request,
    principal: Principal = Depends(require_role("admin")),
) -> dict[str, Any]:
    db = request.app.state.db
    shipment = await _get_shipment_or_404(db, order_id)
    if shipment["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"cannot_assign_from_status:{shipment['status']}",
        )

    rider = await db.riders.find_one({"_id": req.rider_id})
    if rider is None:
        raise HTTPException(status_code=404, detail=f"rider_not_found: {req.rider_id}")

    updated = await db.shipments.find_one_and_update(
        {"_id": order_id, "status": "pending"},
        {"$set": {"status": "assigned", "rider": req.rider_id}},
        return_document=True,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="shipment_already_assigned")

    view = _shipment_view(updated)
    view["notified"] = await _notify(
        db, updated["customer"],
        subject="A rider has been assigned to your order",
        message=f"{rider['name']} is bringing your order {order_id} to "
                f"{updated['address']['line1']}, {updated['address']['city']}.",
    )
    return view


class ShipmentStatusUpdate(BaseModel):
    status: str


@app.patch("/shipments/{order_id}/status")
async def update_shipment_status(
    order_id: str, req: ShipmentStatusUpdate, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    db = request.app.state.db
    shipment = await _get_shipment_or_404(db, order_id)

    if principal.role != "admin" and not (principal.role == "rider" and shipment["rider"] == principal.owner):
        raise HTTPException(status_code=403, detail="not_your_shipment")

    legal_next = SHIPMENT_TRANSITIONS.get(shipment["status"], set())
    if req.status not in legal_next:
        raise HTTPException(
            status_code=409,
            detail=f"illegal_transition: {shipment['status']} -> {req.status} "
                   f"(allowed: {sorted(legal_next) or 'none'})",
        )

    updated = await db.shipments.find_one_and_update(
        {"_id": order_id, "status": shipment["status"]},
        {"$set": {"status": req.status}},
        return_document=True,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="shipment_status_changed_concurrently")

    view = _shipment_view(updated)
    status_messages = {
        "out_for_delivery": "Your order is out for delivery.",
        "delivered": "Your order has been delivered.",
    }
    if req.status in status_messages:
        view["notified"] = await _notify(
            db, updated["customer"],
            subject=f"Order {order_id[:8]} — {req.status.replace('_', ' ')}",
            message=status_messages[req.status],
        )
    return view
