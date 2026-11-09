"""The SaaS client (plan section 7, "SaaS client"): forwards the user's own token, maps failures to
typed errors, retries only idempotent reads, and validates responses. Reads run against the real mock
SaaS over ASGI; failures are injected with httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest
from factories.principals import make_principal
from fakes.clock import FakeClock
from support.specs import need

from services.mock_saas.main import app as mock_saas_app

BASE = "http://mocksaas.test"


def saas_over(transport: httpx.AsyncBaseTransport, *, max_retries: int = 2, sleep=None):  # type: ignore[no-untyped-def]
    client_cls = need("actions.SaaSClient")
    http = httpx.AsyncClient(transport=transport, base_url=BASE)
    return client_cls(http=http, max_retries=max_retries, backoff_seconds=0.5, sleep=sleep)


def mock_saas_transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=mock_saas_app)


class TestAgainstTheMockSaaS:
    async def test_an_overview_read_returns_the_tenants_data(self) -> None:
        principal = make_principal(tenant_id="a0000000-0000-0000-0000-000000000001")
        client = saas_over(mock_saas_transport())
        overview = await client.get_overview(principal)
        assert overview["company_name"] == "Acme Corp"

    async def test_the_users_own_token_is_forwarded_as_a_bearer_token(self) -> None:
        principal = make_principal(tenant_id="a0000000-0000-0000-0000-000000000001")
        captured: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request.headers["authorization"])
            return httpx.Response(
                200,
                json={
                    "tenant_id": "x",
                    "company_name": "x",
                    "plan": "p",
                    "status": "active",
                    "billing_email": "b@x.example",
                },
            )

        await saas_over(httpx.MockTransport(handler)).get_overview(principal)
        assert captured == [f"Bearer {principal.raw_token}"]

    async def test_a_ticket_is_created_for_the_callers_tenant(self) -> None:
        principal = make_principal(tenant_id="a0000000-0000-0000-0000-000000000001")
        ticket = await saas_over(mock_saas_transport()).create_ticket(
            principal, {"subject": "Help", "description": "Escalated from chat", "priority": "high"}
        )
        assert ticket["tenant_id"] == "a0000000-0000-0000-0000-000000000001"


class TestFailureMapping:
    async def test_a_timeout_becomes_a_typed_timeout_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow upstream", request=request)

        with pytest.raises(need("actions.SaaSTimeout")):
            await saas_over(httpx.MockTransport(handler)).get_overview(make_principal())

    async def test_a_404_becomes_a_client_error_with_the_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "Tenant account not found"})

        with pytest.raises(need("actions.SaaSClientError")) as info:
            await saas_over(httpx.MockTransport(handler)).get_overview(make_principal())
        assert info.value.status_code == 404

    async def test_a_client_error_is_not_retried(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(404)

        with pytest.raises(need("actions.SaaSClientError")):
            await saas_over(httpx.MockTransport(handler)).get_overview(make_principal())
        assert len(calls) == 1


class TestRetries:
    async def test_a_server_error_on_a_read_is_retried_then_reported(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(503)

        clock = FakeClock()
        with pytest.raises(need("actions.SaaSUnavailable")):
            await saas_over(
                httpx.MockTransport(handler), max_retries=2, sleep=clock.sleep
            ).get_overview(make_principal())
        assert len(calls) == 3  # first attempt plus two retries

    async def test_retries_back_off_between_attempts(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        clock = FakeClock()
        with pytest.raises(need("actions.SaaSUnavailable")):
            await saas_over(
                httpx.MockTransport(handler), max_retries=2, sleep=clock.sleep
            ).get_overview(make_principal())
        assert len(clock.sleeps) == 2 and clock.sleeps[1] >= clock.sleeps[0]

    async def test_a_server_error_on_a_write_is_not_retried(self) -> None:
        """A POST without an idempotency key must not be replayed: the ticket could be created twice."""
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(500)

        with pytest.raises(need("actions.SaaSUnavailable")):
            await saas_over(httpx.MockTransport(handler)).create_ticket(
                make_principal(), {"subject": "s", "description": "d"}
            )
        assert len(calls) == 1

    async def test_a_transient_failure_that_recovers_returns_the_result(self) -> None:
        responses = iter(
            [
                httpx.Response(503),
                httpx.Response(
                    200,
                    json={
                        "tenant_id": "x",
                        "company_name": "Acme",
                        "plan": "p",
                        "status": "active",
                        "billing_email": "b@x.example",
                    },
                ),
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return next(responses)

        clock = FakeClock()
        overview = await saas_over(
            httpx.MockTransport(handler), max_retries=2, sleep=clock.sleep
        ).get_overview(make_principal())
        assert overview["company_name"] == "Acme"


class TestResponseValidation:
    async def test_a_200_with_the_wrong_shape_is_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        with pytest.raises(need("actions.SaaSResponseInvalid")):
            await saas_over(httpx.MockTransport(handler)).get_overview(make_principal())

    async def test_a_200_that_is_not_json_is_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>maintenance</html>")

        with pytest.raises(need("actions.SaaSResponseInvalid")):
            await saas_over(httpx.MockTransport(handler)).get_overview(make_principal())
