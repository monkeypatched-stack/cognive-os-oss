"""GroceryCapability — a real cognitiveos capability backed by a real,
locally running HTTP service (examples/grocery_service.py). Not a mock:
this makes a genuine authenticated httpx request and gets back whatever the
service actually decided (confirmed order, out of stock, unauthorized, ...).
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx


class GroceryCapability:
    """Parses a quantity + item out of the raw command and places a real,
    authenticated order against the grocery service over HTTP.

    Args:
        name: the cognitiveos capability name to register this under
              (must match the plan step it should handle, e.g. "process_milk").
        base_url: where the grocery service is running.
        api_key: the caller's grocery-service API key (customer role is
                 sufficient to place orders). Defaults to the
                 GROCERY_CUSTOMER_API_KEY env var.
        item: force a specific item (skip parsing it from the command).
        address: delivery address — orders now require one since every
                 confirmed order gets a real shipment. cognitiveos doesn't
                 parse an address out of free text, so this is supplied by
                 whoever registers the capability (e.g. from the actor's
                 own address/profile), not derived from the command.
    """

    def __init__(
        self,
        name: str,
        base_url: str = "http://127.0.0.1:8834",
        api_key: str | None = None,
        item: str | None = None,
        address: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("GROCERY_CUSTOMER_API_KEY")
        self.item = item
        self.address = address or {"line1": "1 Demo St", "city": "Springfield", "postal_code": "00000"}
        self.timeout = timeout

    def fn(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return {
                "success": False,
                "error": "grocery_api_key_missing",
                "detail": "Set GROCERY_CUSTOMER_API_KEY (see grocery_service.py's seeded log line) or pass api_key=.",
            }

        context = kwargs.get("context")
        question = context.question if context is not None else ""

        match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:liters?|dozens?|loaves?|units?)?\s*(?:of\s+)?(\w+)",
            question, re.IGNORECASE,
        )
        if not match:
            return {"success": False, "error": "could_not_parse_request"}

        quantity = float(match.group(1))
        item = self.item or match.group(2).lower()

        try:
            response = httpx.post(
                f"{self.base_url}/orders",
                json={"item": item, "quantity": quantity, "address": self.address},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            return {"success": False, "error": "grocery_service_unreachable", "detail": str(exc)}

        if response.status_code >= 400:
            return {
                "success": False,
                "error": f"grocery_service_http_{response.status_code}",
                "detail": response.text,
            }

        return {"success": True, **response.json()}
