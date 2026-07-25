"""Buying groceries as a real dependency graph, not a single capability
call — the "graph" execution mode from os.py's run(), applied to
grocery_service.py's actual endpoints (auth + MongoDB + atomic
stock/payment transaction + real shipment lifecycle, see
grocery_service.py's own docstring).

The DAG:

    check_wallet ──┐
                    ├──> place_order ──> assign_rider
    check_product ─┘

check_wallet and check_product have no dependency on each other — two
independent, real GET requests — so "graph" mode schedules them
concurrently via asyncio.gather (see os.py's _run_graph). place_order
only runs once *both* preflight checks have completed, reads their
results from state (state.get_data("check_wallet") /
state.get_data("check_product")) rather than re-fetching them, and
refuses to place the order if either check failed.

assign_rider is not synchronous dispatch — real rider assignment needs
an external actor (a dispatcher, human or automated) to actually decide
and act. So this step fires a real OpenClaw system event over the
Gateway's WebSocket (`openclaw system event`, same CLI as
openclaw_agent.py) announcing the order needs a rider, then polls
GET /shipments/{order_id} until something else — main()'s
_simulated_dispatcher() here, a real dispatcher UI in production — calls
POST /shipments/{order_id}/assign. The pipeline step only completes once
that real external assignment has actually happened; a timeout is an
honest failure, not a fabricated one.

Each step hits a genuinely different grocery_service.py endpoint —
this isn't one capability doing everything internally, it's real HTTP
round trips (plus one real WebSocket event) wired together by
cognitiveos's own dependency graph.

Requires grocery_service.py running on :8835 (MongoDB + the seeded
customer/admin API keys — see that file's docstring) with GROCERY_
CUSTOMER_API_KEY / GROCERY_ADMIN_API_KEY set to the keys it logs on
first boot, and the openclaw CLI + Gateway running (see openclaw_agent.py).

Run: pip install -e ".[examples]"; python -m examples.grocery_graph_pipeline
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

import httpx

from cognitiveos import Actor, CognitiveOS


class CheckWalletAgent:
    """Real GET /wallet — no dependencies, safe to run concurrently
    with CheckProductAgent."""

    agent_type = "check_wallet"

    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/wallet",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            return {"success": False, "error": "grocery_service_unreachable", "detail": str(exc)}
        if response.status_code >= 400:
            return {"success": False, "error": f"wallet_http_{response.status_code}"}
        data = response.json()
        return {"success": True, "balance": data["balance"]}


class CheckProductAgent:
    """Real GET /products?q=<item> — no dependencies, safe to run
    concurrently with CheckWalletAgent."""

    agent_type = "check_product"

    def __init__(self, base_url: str, api_key: str, item: str = "milk", timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.item = item
        self.timeout = timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/products",
                    params={"q": self.item},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            return {"success": False, "error": "grocery_service_unreachable", "detail": str(exc)}
        if response.status_code >= 400:
            return {"success": False, "error": f"products_http_{response.status_code}"}
        results = response.json().get("results", [])
        if not results:
            return {"success": False, "error": f"product_not_found: {self.item}"}
        product = results[0]
        return {"success": True, "item": self.item, "price_per_unit": product["price_per_unit"], "stock": product["stock"]}


class PlaceOrderAgent:
    """Real POST /orders — depends_on: [check_wallet, check_product].
    Reads both preflight results from state instead of re-fetching them,
    and refuses to place the order if either preflight failed.
    """

    agent_type = "place_order"

    def __init__(
        self, base_url: str, api_key: str, quantity: float = 3.0, timeout: float = 5.0,
        order_placed_queue: asyncio.Queue | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.quantity = quantity
        self.timeout = timeout
        # Lets a demo dispatcher (see main()) learn the order_id the moment
        # it exists, without polling grocery_service for it.
        self.order_placed_queue = order_placed_queue

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        state = kwargs.get("state")
        wallet = state.get_data("check_wallet") if state is not None else None
        product = state.get_data("check_product") if state is not None else None

        if not wallet or not wallet.get("success"):
            return {"success": False, "error": "wallet_preflight_missing_or_failed"}
        if not product or not product.get("success"):
            return {"success": False, "error": "product_preflight_missing_or_failed"}

        cost = round(self.quantity * product["price_per_unit"], 2)
        if wallet["balance"] < cost:
            return {"success": False, "error": f"insufficient_funds_precheck: have {wallet['balance']}, need {cost}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/orders",
                    json={
                        "item": product["item"], "quantity": self.quantity,
                        "address": {"line1": "1 Demo St", "city": "Springfield", "postal_code": "00000"},
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            return {"success": False, "error": "grocery_service_unreachable", "detail": str(exc)}
        if response.status_code >= 400:
            return {"success": False, "error": f"orders_http_{response.status_code}", "detail": response.text}

        order = response.json()
        if self.order_placed_queue is not None:
            await self.order_placed_queue.put(order["order_id"])
        return {"success": True, "order_id": order["order_id"], "cost": order["cost"], "remaining_stock": order["remaining_stock"]}


class AssignRiderAgent:
    """depends_on: [place_order] — but doesn't assign a rider itself.

    Real dispatch isn't synchronous: a human (or a separate automated
    dispatcher) has to actually pick this up. So this step:
      1. Fires a real OpenClaw system event (`openclaw system event`,
         over the Gateway's WebSocket — see openclaw_agent.py for the
         same CLI, different subcommand) announcing that order_id needs
         a rider. This is the real notification the pipeline sends out.
      2. Polls GET /shipments/{order_id} until its status leaves
         "pending" — i.e. until *something else* calls
         POST /shipments/{order_id}/assign, same as before, just no
         longer called from here.
    The pipeline step only completes once that real external assignment
    has actually happened; a timeout is a real, honest failure ("nobody
    assigned a rider in time"), not a fabricated one.
    """

    agent_type = "assign_rider"

    def __init__(
        self, base_url: str, admin_api_key: str,
        poll_interval: float = 1.0, wait_timeout: float = 30.0, http_timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_api_key = admin_api_key
        self.poll_interval = poll_interval
        self.wait_timeout = wait_timeout
        self.http_timeout = http_timeout

    async def handle(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        state = kwargs.get("state")
        order = state.get_data("place_order") if state is not None else None
        if not order or not order.get("success"):
            return {"success": False, "error": "order_missing_or_failed"}
        order_id = order["order_id"]

        notified = await self._notify_openclaw(order_id)

        deadline = time.monotonic() + self.wait_timeout
        headers = {"Authorization": f"Bearer {self.admin_api_key}"}
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            while time.monotonic() < deadline:
                try:
                    response = await client.get(f"{self.base_url}/shipments/{order_id}", headers=headers)
                except httpx.HTTPError as exc:
                    return {"success": False, "error": "grocery_service_unreachable", "detail": str(exc)}

                if response.status_code >= 400:
                    return {"success": False, "error": f"shipment_http_{response.status_code}", "detail": response.text}

                shipment = response.json()
                if shipment["status"] != "pending":
                    return {
                        "success": True, "shipment_id": shipment["shipment_id"],
                        "status": shipment["status"], "rider": shipment["rider"],
                        "notified_dispatcher": notified,
                    }
                await asyncio.sleep(self.poll_interval)

        return {"success": False, "error": "timeout_waiting_for_rider_assignment", "notified_dispatcher": notified}

    async def _notify_openclaw(self, order_id: str) -> bool:
        """Real WebSocket event to the OpenClaw Gateway — `openclaw system
        event` (see openclaw --help: "System events, heartbeat, and
        presence"). Never blocks the wait loop on notification failure;
        a dispatcher missing the notification is a different problem
        from nobody ever assigning the rider.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "openclaw", "system", "event",
                "--text", f"New grocery order {order_id} needs a rider assigned "
                          f"(POST /shipments/{order_id}/assign).",
                "--mode", "now",
                "--json",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return proc.returncode == 0 and b'"ok":true' in stdout.replace(b" ", b"")
        except Exception:
            return False


class GroceryGraphEngine:
    async def tick(self, actor: Any) -> dict:
        return {
            "plan": {
                "execution": "graph",
                "steps": [
                    {"name": "check_wallet", "type": "agent"},
                    {"name": "check_product", "type": "agent"},
                    {"name": "place_order", "type": "agent", "depends_on": ["check_wallet", "check_product"]},
                    {"name": "assign_rider", "type": "agent", "depends_on": ["place_order"]},
                ],
            },
        }


async def _simulated_dispatcher(base_url: str, admin_key: str, order_placed_queue: asyncio.Queue, rider_id: str = "rider1") -> None:
    """Stands in for the human (or automated) dispatcher who'd actually
    see the OpenClaw notification and act on it. Waits for place_order
    to hand it a real order_id, pauses a moment (as if reading the
    notification and deciding), then makes the real assignment call
    AssignRiderAgent no longer makes itself.
    """
    order_id = await order_placed_queue.get()
    await asyncio.sleep(2.0)
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{base_url}/shipments/{order_id}/assign",
            json={"rider_id": rider_id},
            headers={"Authorization": f"Bearer {admin_key}"},
        )
    print(f"  [dispatcher] assigned {rider_id} to order {order_id} -> HTTP {response.status_code}")


async def main() -> None:
    base_url = "http://127.0.0.1:8835"
    customer_key = os.environ["GROCERY_CUSTOMER_API_KEY"]
    admin_key = os.environ["GROCERY_ADMIN_API_KEY"]

    actor = Actor(entity_id="alice", actor_type_id="human", name="Alice", goals=["wealth"])
    order_placed_queue: asyncio.Queue = asyncio.Queue()

    os_ = CognitiveOS()
    os_.set_actor(actor)
    os_.register_agent(CheckWalletAgent(base_url, customer_key))
    os_.register_agent(CheckProductAgent(base_url, customer_key, item="milk"))
    os_.register_agent(PlaceOrderAgent(base_url, customer_key, quantity=3.0, order_placed_queue=order_placed_queue))
    os_.register_agent(AssignRiderAgent(base_url, admin_key, poll_interval=1.0, wait_timeout=30.0))
    os_.set_engine(GroceryGraphEngine())

    dispatcher_task = asyncio.create_task(_simulated_dispatcher(base_url, admin_key, order_placed_queue))

    start = time.monotonic()
    result = await os_.run("Buy 3 liters of milk")
    elapsed = time.monotonic() - start
    await dispatcher_task

    print("Parsed intent:", result.intent)
    for sr in result.step_results:
        print(f"  {sr.action:15s} -> {sr.status:8s} {sr.output}")
    print(f"\nOverall success: {result.success}  ({elapsed:.2f}s wall clock — assign_rider genuinely")
    print("waited for the dispatcher's real assignment call, it didn't make one itself)")


if __name__ == "__main__":
    asyncio.run(main())
