"""InstacartDeliveryCapability — a real cognitiveos capability backed by the
real Instacart Connect Fulfillment API (not a mock).

    POST https://connect.instacart.com/v2/fulfillment/users/{user_id}/orders/delivery

Schema per https://docs.instacart.com/connect/api/fulfillment/delivery/create_order —
Bearer-token OAuth, items identified by UPC/RRC with count or weight. This is a
business-partner-gated API (see https://docs.instacart.com/connect: "Contact us
to discuss your requirements with an Instacart Connect representative") — there
is no self-service API key. Without INSTACART_API_TOKEN / INSTACART_USER_ID set,
this capability honestly reports "not configured" rather than faking an order.

Requires the `examples` extra: pip install -e ".[examples]" (adds httpx).
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx


class InstacartDeliveryCapability:
    """Places a real delivery order through Instacart Connect for one item.

    Args:
        name: the cognitiveos capability name to register this under
              (must match the plan step it should handle, e.g. "process_milk").
        upc: the product's UPC in Instacart's catalog (Instacart Connect
             identifies items by UPC/RRC, not free-text names — resolving
             "milk" to a UPC requires Instacart's catalog/search API, which
             is out of scope here; pass the UPC directly).
        count: how many units to order.
        address: delivery address dict — address_line_1 (required),
                 address_line_2, postal_code, city.
        api_token: Instacart Connect OAuth bearer token. Defaults to the
                   INSTACART_API_TOKEN env var.
        user_id: the Instacart Connect user_id path parameter. Defaults to
                 the INSTACART_USER_ID env var.
    """

    BASE_URL = "https://connect.instacart.com/v2"

    def __init__(
        self,
        name: str,
        upc: str,
        count: int = 1,
        address: dict[str, Any] | None = None,
        api_token: str | None = None,
        user_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.name = name
        self.upc = upc
        self.count = count
        self.address = address or {}
        self.api_token = api_token or os.environ.get("INSTACART_API_TOKEN")
        self.user_id = user_id or os.environ.get("INSTACART_USER_ID")
        self.timeout = timeout

    def fn(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if not self.api_token or not self.user_id:
            return {
                "success": False,
                "error": "instacart_not_configured",
                "detail": (
                    "Set INSTACART_API_TOKEN and INSTACART_USER_ID — Instacart "
                    "Connect requires an approved partner account, there is no "
                    "self-service key. See https://docs.instacart.com/connect."
                ),
            }

        url = f"{self.BASE_URL}/fulfillment/users/{self.user_id}/orders/delivery"
        payload = {
            "order_id": f"cognitiveos-{int(time.time())}",
            "address": self.address,
            "items": [
                {"line_num": "1", "count": self.count, "item": {"upc": self.upc}},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            return {"success": False, "error": "instacart_request_failed", "detail": str(exc)}

        if response.status_code >= 400:
            return {
                "success": False,
                "error": f"instacart_http_{response.status_code}",
                "detail": response.text[:500],
            }

        data = response.json()
        return {
            "success": True,
            "order_id": data.get("id"),
            "status": data.get("status"),
            "raw": data,
        }
