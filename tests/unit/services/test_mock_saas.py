"""Mock SaaS service: tenant-isolated account data, billing e-mail change and helpdesk tickets.

It stands in for the customer's real SaaS, so the agent's tools are only as trustworthy as this
service's own access control. Tests assert the *specified* behaviour; known gaps are DEFECT-04..06.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import httpx
import pytest
from factories.principals import auth_header, forge_token, make_token
from support.spec import DEMO_TENANT_A_ID, DEMO_TENANT_B_ID

from ragassist.shared.security.jwt import UserRole


def headers_for(tenant: str, role: UserRole = UserRole.USER) -> dict[str, str]:
    return auth_header(make_token(tenant_id=tenant, role=role))  # type: ignore[arg-type]


@pytest.fixture
def acme() -> dict[str, str]:
    return headers_for(DEMO_TENANT_A_ID)


@pytest.fixture
def acme_admin() -> dict[str, str]:
    return headers_for(DEMO_TENANT_A_ID, UserRole.ADMIN)


@pytest.fixture
def globex() -> dict[str, str]:
    return headers_for(DEMO_TENANT_B_ID)


class TestHealth:
    async def test_healthz_needs_no_credentials(self, mock_saas_client: httpx.AsyncClient) -> None:
        response = await mock_saas_client.get("/healthz")
        assert response.status_code == 200 and response.json() == {"status": "ok"}


class TestAuthentication:
    PROTECTED = [
        ("GET", "/accounts/overview"),
        ("GET", "/accounts/subscription"),
        ("GET", "/accounts/invoices"),
        ("POST", "/accounts/billing-email"),
        ("POST", "/helpdesk/tickets"),
    ]

    @pytest.mark.parametrize(("method", "path"), PROTECTED)
    async def test_requests_without_a_token_are_rejected(
        self, mock_saas_client: httpx.AsyncClient, method: str, path: str
    ) -> None:
        response = await mock_saas_client.request(method, path, json={})
        assert response.status_code == 401

    @pytest.mark.parametrize(("method", "path"), PROTECTED)
    async def test_garbage_tokens_are_rejected(
        self, mock_saas_client: httpx.AsyncClient, method: str, path: str
    ) -> None:
        response = await mock_saas_client.request(
            method, path, json={}, headers=auth_header("not-a-jwt")
        )
        assert response.status_code == 401

    async def test_token_without_a_tenant_claim_is_rejected(
        self, mock_saas_client: httpx.AsyncClient
    ) -> None:
        token = forge_token(drop=("tenant_id",))
        assert (
            await mock_saas_client.get("/accounts/overview", headers=auth_header(token))
        ).status_code == 401

    async def test_the_error_does_not_reveal_why(self, mock_saas_client: httpx.AsyncClient) -> None:
        response = await mock_saas_client.get("/accounts/overview", headers=auth_header("x.y.z"))
        assert response.json() == {"detail": "Invalid token"}

    async def test_token_signed_with_the_wrong_key_is_rejected(
        self, mock_saas_client: httpx.AsyncClient
    ) -> None:
        token = forge_token(
            key="attacker-controlled-key-0123456789abcdefghijklmnop",
            claims={"tenant_id": DEMO_TENANT_A_ID},
        )
        assert (
            await mock_saas_client.get("/accounts/overview", headers=auth_header(token))
        ).status_code == 401

    async def test_expired_token_is_rejected(self, mock_saas_client: httpx.AsyncClient) -> None:
        token = make_token(
            tenant_id=DEMO_TENANT_A_ID, expires_delta=__import__("datetime").timedelta(minutes=-5)
        )  # type: ignore[arg-type]
        assert (
            await mock_saas_client.get("/accounts/overview", headers=auth_header(token))
        ).status_code == 401

    async def test_unsigned_alg_none_token_is_rejected(
        self, mock_saas_client: httpx.AsyncClient
    ) -> None:
        token = forge_token(algorithm="none", claims={"tenant_id": DEMO_TENANT_A_ID})
        assert (
            await mock_saas_client.get("/accounts/overview", headers=auth_header(token))
        ).status_code == 401


class TestReads:
    async def test_overview(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        body = (await mock_saas_client.get("/accounts/overview", headers=acme)).json()
        assert body == {
            "tenant_id": DEMO_TENANT_A_ID,
            "company_name": "Acme Corp",
            "plan": "Enterprise Scale",
            "status": "active",
            "billing_email": "billing@acme.example.com",
        }

    async def test_subscription(
        self, mock_saas_client: httpx.AsyncClient, globex: dict[str, str]
    ) -> None:
        body = (await mock_saas_client.get("/accounts/subscription", headers=globex)).json()
        assert (body["plan"], body["seats"], body["seats_used"]) == ("Pro Starter", 10, 9)
        assert body["seats_used"] <= body["seats"]

    async def test_invoices(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        invoices = (await mock_saas_client.get("/accounts/invoices", headers=acme)).json()
        assert [i["id"] for i in invoices] == ["inv_acme_101", "inv_acme_102"]
        assert all({"id", "amount", "status", "date"} <= set(i) for i in invoices)

    async def test_each_tenant_sees_only_its_own_invoices(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str], globex: dict[str, str]
    ) -> None:
        a = (await mock_saas_client.get("/accounts/invoices", headers=acme)).json()
        b = (await mock_saas_client.get("/accounts/invoices", headers=globex)).json()
        assert {i["id"] for i in a}.isdisjoint({i["id"] for i in b})
        assert all("globex" not in i["id"] for i in a) and all("acme" not in i["id"] for i in b)

    @pytest.mark.parametrize(
        "path", ["/accounts/overview", "/accounts/subscription", "/accounts/invoices"]
    )
    async def test_unknown_tenant_gets_404_not_someone_elses_data(
        self, mock_saas_client: httpx.AsyncClient, path: str
    ) -> None:
        response = await mock_saas_client.get(path, headers=headers_for(str(uuid4())))
        assert response.status_code == 404

    async def test_the_tenant_comes_from_the_token_not_from_query_parameters(
        self, mock_saas_client: httpx.AsyncClient, globex: dict[str, str]
    ) -> None:
        body = (
            await mock_saas_client.get(
                f"/accounts/overview?tenant_id={DEMO_TENANT_A_ID}", headers=globex
            )
        ).json()
        assert body["company_name"] == "Globex Corp"

    async def test_reads_do_not_change_state(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        first = (await mock_saas_client.get("/accounts/invoices", headers=acme)).json()
        second = (await mock_saas_client.get("/accounts/invoices", headers=acme)).json()
        assert first == second


class TestBillingEmail:
    async def test_admin_can_change_the_billing_email(
        self, mock_saas_client: httpx.AsyncClient, acme_admin: dict[str, str]
    ) -> None:
        response = await mock_saas_client.post(
            "/accounts/billing-email", json={"new_email": "ap@acme.example.com"}, headers=acme_admin
        )
        assert response.status_code == 200
        assert response.json() == {
            "status": "success",
            "tenant_id": DEMO_TENANT_A_ID,
            "updated_billing_email": "ap@acme.example.com",
        }

    async def test_the_change_is_visible_afterwards(
        self, mock_saas_client: httpx.AsyncClient, acme_admin: dict[str, str]
    ) -> None:
        await mock_saas_client.post(
            "/accounts/billing-email",
            json={"new_email": "new@acme.example.com"},
            headers=acme_admin,
        )
        overview = (await mock_saas_client.get("/accounts/overview", headers=acme_admin)).json()
        assert overview["billing_email"] == "new@acme.example.com"

    async def test_changing_one_tenant_never_changes_another(
        self,
        mock_saas_client: httpx.AsyncClient,
        acme_admin: dict[str, str],
        globex: dict[str, str],
    ) -> None:
        before = (await mock_saas_client.get("/accounts/overview", headers=globex)).json()
        await mock_saas_client.post(
            "/accounts/billing-email", json={"new_email": "x@acme.example.com"}, headers=acme_admin
        )
        assert (await mock_saas_client.get("/accounts/overview", headers=globex)).json() == before

    async def test_unknown_tenant_cannot_create_an_account_by_updating(
        self, mock_saas_client: httpx.AsyncClient
    ) -> None:
        response = await mock_saas_client.post(
            "/accounts/billing-email",
            json={"new_email": "a@b.example"},
            headers=headers_for(str(uuid4()), UserRole.ADMIN),
        )
        assert response.status_code == 404

    async def test_a_tenant_id_in_the_body_is_ignored(
        self,
        mock_saas_client: httpx.AsyncClient,
        acme_admin: dict[str, str],
        globex: dict[str, str],
    ) -> None:
        before = (await mock_saas_client.get("/accounts/overview", headers=globex)).json()
        await mock_saas_client.post(
            "/accounts/billing-email",
            json={"new_email": "x@acme.example.com", "tenant_id": DEMO_TENANT_B_ID},
            headers=acme_admin,
        )
        assert (await mock_saas_client.get("/accounts/overview", headers=globex)).json() == before

    @pytest.mark.parametrize(
        "payload", [{}, {"new_email": None}, {"new_email": 5}, {"email": "a@b.example"}]
    )
    async def test_malformed_bodies_get_422(
        self, mock_saas_client: httpx.AsyncClient, acme_admin: dict[str, str], payload: dict
    ) -> None:
        assert (
            await mock_saas_client.post("/accounts/billing-email", json=payload, headers=acme_admin)
        ).status_code == 422

    async def test_a_plain_user_cannot_change_the_billing_email(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        response = await mock_saas_client.post(
            "/accounts/billing-email", json={"new_email": "thief@evil.example"}, headers=acme
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("email", ["not-an-email", "a@", "@b.example", "a b@c.example", ""])
    async def test_invalid_email_addresses_are_rejected(
        self, mock_saas_client: httpx.AsyncClient, acme_admin: dict[str, str], email: str
    ) -> None:
        response = await mock_saas_client.post(
            "/accounts/billing-email", json={"new_email": email}, headers=acme_admin
        )
        assert response.status_code == 422


class TestTickets:
    PAYLOAD = {"subject": "Cannot log in", "description": "Reset e-mail never arrives"}

    async def test_creates_an_open_high_priority_ticket(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        response = await mock_saas_client.post("/helpdesk/tickets", json=self.PAYLOAD, headers=acme)
        assert response.status_code == 200
        ticket = response.json()
        assert ticket["status"] == "open" and ticket["priority"] == "high"
        assert (
            ticket["subject"] == self.PAYLOAD["subject"]
            and ticket["description"] == self.PAYLOAD["description"]
        )
        assert ticket["conversation_id"] is None

    async def test_tenant_comes_from_the_token(
        self, mock_saas_client: httpx.AsyncClient, globex: dict[str, str]
    ) -> None:
        ticket = (
            await mock_saas_client.post(
                "/helpdesk/tickets",
                json={**self.PAYLOAD, "tenant_id": DEMO_TENANT_A_ID},
                headers=globex,
            )
        ).json()
        assert ticket["tenant_id"] == DEMO_TENANT_B_ID

    async def test_conversation_id_and_priority_are_stored(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        conversation = str(uuid4())
        ticket = (
            await mock_saas_client.post(
                "/helpdesk/tickets",
                json={**self.PAYLOAD, "conversation_id": conversation, "priority": "low"},
                headers=acme,
            )
        ).json()
        assert (ticket["conversation_id"], ticket["priority"]) == (conversation, "low")

    async def test_ids_are_sequential_and_well_formed(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        ids = [
            (
                await mock_saas_client.post("/helpdesk/tickets", json=self.PAYLOAD, headers=acme)
            ).json()["id"]
            for _ in range(3)
        ]
        assert ids == ["TICK-0001", "TICK-0002", "TICK-0003"]

    async def test_ids_stay_unique_under_concurrent_creation(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        responses = await asyncio.gather(
            *[
                mock_saas_client.post("/helpdesk/tickets", json=self.PAYLOAD, headers=acme)
                for _ in range(50)
            ]
        )
        ids = [r.json()["id"] for r in responses]
        assert len(set(ids)) == 50

    async def test_created_at_is_an_aware_utc_timestamp(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        from datetime import datetime, timedelta

        stamp = datetime.fromisoformat(
            (
                await mock_saas_client.post("/helpdesk/tickets", json=self.PAYLOAD, headers=acme)
            ).json()["created_at"]
        )
        assert stamp.utcoffset() == timedelta(0)

    @pytest.mark.parametrize(
        "payload", [{}, {"subject": "only subject"}, {"description": "only description"}]
    )
    async def test_subject_and_description_are_required(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str], payload: dict
    ) -> None:
        assert (
            await mock_saas_client.post("/helpdesk/tickets", json=payload, headers=acme)
        ).status_code == 422

    async def test_unicode_and_long_text_round_trip(
        self, mock_saas_client: httpx.AsyncClient, acme: dict[str, str]
    ) -> None:
        text = "问题 🚨 " + "x" * 20_000
        ticket = (
            await mock_saas_client.post(
                "/helpdesk/tickets", json={"subject": "s", "description": text}, headers=acme
            )
        ).json()
        assert ticket["description"] == text
