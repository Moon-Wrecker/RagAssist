"""SaaS Client adapter calling the Mock SaaS service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
import httpx

from ragassist.shared.domain import DomainError
from ragassist.shared.security.jwt import Principal


class SaaSClientError(DomainError):
    """Raised on 4xx responses from SaaS service."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class SaaSUnavailable(DomainError):
    """Raised on 5xx responses after all retries are exhausted."""


class SaaSTimeout(DomainError):
    """Raised when request to SaaS service times out."""


class SaaSResponseInvalid(DomainError):
    """Raised when SaaS service returns 2xx with non-JSON or invalid schema."""


class SaaSClient:
    """Async HTTP client for SaaS service with tenant JWT forwarding and retries."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        max_retries: int = 2,
        backoff_seconds: float = 0.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._http = http
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep or asyncio.sleep

    def _headers(self, principal: Principal) -> dict[str, str]:
        token = getattr(principal, "raw_token", str(principal.tenant_id))
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def _send(
        self,
        method: str,
        path: str,
        principal: Principal,
        *,
        json: Any = None,
        is_write: bool = False,
    ) -> Any:
        headers = self._headers(principal)
        max_attempts = 1 if is_write else 1 + self._max_retries

        for attempt in range(max_attempts):
            try:
                response = await self._http.request(
                    method=method,
                    url=path,
                    headers=headers,
                    json=json,
                )
            except httpx.TimeoutException as exc:
                raise SaaSTimeout(f"Request to {path} timed out") from exc
            except httpx.RequestError as exc:
                if attempt + 1 >= max_attempts:
                    raise SaaSUnavailable(f"Request failed: {exc}") from exc
                delay = self._backoff_seconds * (2**attempt)
                if delay > 0:
                    await self._sleep(delay)
                continue

            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except Exception as exc:
                    raise SaaSResponseInvalid(f"Response from {path} is not valid JSON") from exc

            if 400 <= response.status_code < 500:
                raise SaaSClientError(
                    f"Client error {response.status_code} for {path}: {response.text}",
                    status_code=response.status_code,
                )

            if response.status_code >= 500:
                if is_write or (attempt + 1 >= max_attempts):
                    raise SaaSUnavailable(
                        f"Server error {response.status_code} for {path}: {response.text}"
                    )
                delay = self._backoff_seconds * (2**attempt)
                if delay > 0:
                    await self._sleep(delay)
                continue

        raise SaaSUnavailable(f"Server unavailable for {path} after retries")

    async def get_overview(self, principal: Principal) -> dict[str, Any]:
        data = await self._send("GET", "/accounts/overview", principal, is_write=False)
        required = {"tenant_id", "company_name", "plan", "status", "billing_email"}
        if not isinstance(data, dict) or not required.issubset(data.keys()):
            raise SaaSResponseInvalid("Overview response missing required fields")
        return data

    async def get_subscription(self, principal: Principal) -> dict[str, Any]:
        data = await self._send("GET", "/accounts/subscription", principal, is_write=False)
        required = {"tenant_id", "plan", "seats", "seats_used", "monthly_spend", "subscription_renews"}
        if not isinstance(data, dict) or not required.issubset(data.keys()):
            raise SaaSResponseInvalid("Subscription response missing required fields")
        return data

    async def get_invoices(self, principal: Principal) -> list[dict[str, Any]]:
        data = await self._send("GET", "/accounts/invoices", principal, is_write=False)
        if not isinstance(data, list):
            raise SaaSResponseInvalid("Invoices response must be a list")
        return data

    async def update_billing_email(self, principal: Principal, new_email: str) -> dict[str, Any]:
        data = await self._send(
            "POST",
            "/accounts/billing-email",
            principal,
            json={"new_email": new_email},
            is_write=True,
        )
        required = {"status", "tenant_id", "updated_billing_email"}
        if not isinstance(data, dict) or not required.issubset(data.keys()):
            raise SaaSResponseInvalid("Update billing email response missing required fields")
        return data

    async def create_ticket(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._send(
            "POST",
            "/helpdesk/tickets",
            principal,
            json=payload,
            is_write=True,
        )
        if not isinstance(data, dict) or "id" not in data:
            raise SaaSResponseInvalid("Ticket creation response missing ticket id")
        return data
