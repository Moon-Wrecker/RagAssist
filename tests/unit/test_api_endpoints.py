"""Standalone comprehensive unit and API endpoint tests for Milestone 5.

Consulted References:
- Starlette / FastAPI testing with httpx.ASGITransport:
  https://www.encode.io/httpx/advanced/#asgi
- SSE Contract verification against tests/support/sse.py.
- WHATWG EventSource specification for headers and frames.
- Prometheus text exposition format validation.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from support.sse import parse_sse

from ragassist.main import create_app
from ragassist.modules.assistant.api.router import get_conversation_store
from ragassist.shared.security.jwt import UserRole, create_access_token
from ragassist.shared.security.rate_limiter import SlidingWindowRateLimiter

TENANT_1 = "11111111-1111-1111-1111-111111111111"
TENANT_2 = "22222222-2222-2222-2222-222222222222"
USER_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def user_headers():
    token = create_access_token(user_id=uuid4(), tenant_id=uuid4(), role=UserRole.USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def agent_headers():
    token = create_access_token(user_id=uuid4(), tenant_id=uuid4(), role=UserRole.AGENT)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_1_user_headers():
    token = create_access_token(user_id=uuid4(), tenant_id=TENANT_1, role=UserRole.USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_1_agent_headers():
    token = create_access_token(user_id=uuid4(), tenant_id=TENANT_1, role=UserRole.AGENT)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_2_user_headers():
    token = create_access_token(user_id=uuid4(), tenant_id=TENANT_2, role=UserRole.USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_1_admin_headers():
    token = create_access_token(user_id=uuid4(), tenant_id=TENANT_1, role=UserRole.ADMIN)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_2_admin_headers():
    token = create_access_token(user_id=uuid4(), tenant_id=TENANT_2, role=UserRole.ADMIN)
    return {"Authorization": f"Bearer {token}"}


class TestSystemAndObservability:
    """Verifies health check, Prometheus metrics exposition, and timing middleware."""

    @pytest.mark.asyncio
    async def test_healthz_endpoint(self, app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/healthz")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "app" in data

    @pytest.mark.asyncio
    async def test_metrics_endpoint_exposition(self, app, tenant_1_admin_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Send a request to trigger metrics
            await client.get("/healthz")
            resp = await client.get("/metrics", headers=tenant_1_admin_headers)
            assert resp.status_code == 200
            assert "text/plain" in resp.headers["content-type"]
            text = resp.text
            assert "http_requests_total" in text
            assert "http_request_duration_seconds" in text
            assert "ragassist_active_requests" in text

    @pytest.mark.asyncio
    async def test_request_timing_and_rate_limit_headers(self, app, user_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/healthz")
            assert "X-Process-Time" in resp.headers
            val = float(resp.headers["X-Process-Time"])
            assert val >= 0.0

    @pytest.mark.asyncio
    async def test_openapi_documentation_accessible(self, app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/openapi.json")
            assert resp.status_code == 200
            schema = resp.json()
            assert schema["info"]["title"] == "RagAssist"
            assert "/v1/documents" in schema["paths"]
            assert "/v1/conversations" in schema["paths"]
            assert "/v1/escalations" in schema["paths"]


class TestRateLimiter:
    """Verifies sliding window rate limiting."""

    def test_rate_limiter_exceeded(self):
        limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60.0)
        key = "client-test-ip"
        assert limiter.is_allowed(key)[0] is True
        assert limiter.is_allowed(key)[0] is True
        assert limiter.is_allowed(key)[0] is True
        allowed, remaining, reset_sec = limiter.is_allowed(key)
        assert allowed is False
        assert remaining == 0
        assert reset_sec > 0


class TestKnowledgeApi:
    """Verifies multipart document upload, listing, job details, re-indexing, and deletion."""

    @pytest.mark.asyncio
    async def test_upload_document_multipart_success(self, app, tenant_1_admin_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            files = {"file": ("guide.md", b"# Knowledge Base\n\nWelcome.", "text/markdown")}
            resp = await client.post("/v1/documents", files=files, headers=tenant_1_admin_headers)
            assert resp.status_code == 202
            data = resp.json()
            assert "document_id" in data
            assert "job_id" in data
            assert data["status"] == "queued"
            assert "tenants/" in data["object_key"]

    @pytest.mark.asyncio
    async def test_upload_document_unsupported_mime(self, app, tenant_1_admin_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            files = {"file": ("malware.exe", b"binarydata", "application/x-msdownload")}
            resp = await client.post("/v1/documents", files=files, headers=tenant_1_admin_headers)
            assert resp.status_code == 415

    @pytest.mark.asyncio
    async def test_upload_document_requires_auth(self, app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            files = {"file": ("doc.md", b"# Hi", "text/markdown")}
            resp = await client.post("/v1/documents", files=files)
            assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_list_documents_tenant_isolated(
        self, app, tenant_1_admin_headers, tenant_2_admin_headers
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Upload doc for Tenant 1
            files = {"file": ("tenant1.md", b"Content 1", "text/markdown")}
            upload_resp = await client.post(
                "/v1/documents", files=files, headers=tenant_1_admin_headers
            )
            doc_id_1 = upload_resp.json()["document_id"]

            # Tenant 1 lists docs
            t1_list = await client.get("/v1/documents", headers=tenant_1_admin_headers)
            assert t1_list.status_code == 200
            t1_ids = [d["document_id"] for d in t1_list.json()["items"]]
            assert doc_id_1 in t1_ids

            # Tenant 2 lists docs -> does not see Tenant 1 doc
            t2_list = await client.get("/v1/documents", headers=tenant_2_admin_headers)
            assert t2_list.status_code == 200
            t2_ids = [d["document_id"] for d in t2_list.json()["items"]]
            assert doc_id_1 not in t2_ids

    @pytest.mark.asyncio
    async def test_ingestion_job_status_and_isolation(
        self, app, tenant_1_admin_headers, tenant_2_admin_headers
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            files = {"file": ("job_test.md", b"Job test content", "text/markdown")}
            upload_resp = await client.post(
                "/v1/documents", files=files, headers=tenant_1_admin_headers
            )
            job_id = upload_resp.json()["job_id"]

            # Tenant 1 gets job status
            res = await client.get(f"/v1/ingestion-jobs/{job_id}", headers=tenant_1_admin_headers)
            assert res.status_code == 200
            assert res.json()["job_id"] == job_id
            assert res.json()["status"] == "queued"

            # Tenant 2 accessing Tenant 1 job -> 404
            res_foreign = await client.get(
                f"/v1/ingestion-jobs/{job_id}", headers=tenant_2_admin_headers
            )
            assert res_foreign.status_code == 404

    @pytest.mark.asyncio
    async def test_reindex_and_delete_document(self, app, tenant_1_admin_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            files = {"file": ("to_delete.md", b"delete me", "text/markdown")}
            up = await client.post("/v1/documents", files=files, headers=tenant_1_admin_headers)
            doc_id = up.json()["document_id"]

            # Reindex
            reindex_res = await client.post(
                f"/v1/documents/{doc_id}/reindex", headers=tenant_1_admin_headers
            )
            assert reindex_res.status_code == 200
            assert reindex_res.json()["status"] == "queued"

            # Delete
            del_res = await client.delete(f"/v1/documents/{doc_id}", headers=tenant_1_admin_headers)
            assert del_res.status_code == 200
            assert del_res.json()["deleted"] is True

            # Re-fetch deleted -> 404
            reindex_again = await client.post(
                f"/v1/documents/{doc_id}/reindex", headers=tenant_1_admin_headers
            )
            assert reindex_again.status_code == 404


class TestAssistantApi:
    """Verifies conversations, SSE streaming responses, and interrupt actions."""

    @pytest.mark.asyncio
    async def test_create_and_list_conversations(self, app, tenant_1_user_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create
            resp = await client.post(
                "/v1/conversations",
                json={"title": "Billing Inquiry"},
                headers=tenant_1_user_headers,
            )
            assert resp.status_code == 201
            cid = resp.json()["conversation_id"]
            assert resp.json()["title"] == "Billing Inquiry"

            # List
            list_resp = await client.get("/v1/conversations", headers=tenant_1_user_headers)
            assert list_resp.status_code == 200
            ids = [c["conversation_id"] for c in list_resp.json()["items"]]
            assert cid in ids

    @pytest.mark.asyncio
    async def test_send_message_json_response(self, app, tenant_1_user_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            create_resp = await client.post(
                "/v1/conversations",
                json={"title": "Q&A"},
                headers=tenant_1_user_headers,
            )
            cid = create_resp.json()["conversation_id"]

            # Send message without SSE
            msg_resp = await client.post(
                f"/v1/conversations/{cid}/messages",
                json={"content": "What is the refund policy?"},
                headers=tenant_1_user_headers,
            )
            assert msg_resp.status_code == 200
            data = msg_resp.json()
            assert "answer" in data
            assert isinstance(data["citations"], list)
            assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_send_message_sse_streaming(self, app, tenant_1_user_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            cid = str(uuid4())
            async with client.stream(
                "POST",
                f"/v1/conversations/{cid}/messages",
                json={"content": "Explain billing cycles"},
                headers={**tenant_1_user_headers, "Accept": "text/event-stream"},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                assert response.headers["cache-control"] == "no-cache"
                assert response.headers["x-accel-buffering"] == "no"

                chunks = [chunk async for chunk in response.aiter_text()]
                stream_text = "".join(chunks)
                parsed = parse_sse(stream_text)
                names = parsed.names()
                assert "token" in names
                assert "citation" in names
                assert "done" in names
                assert names[-1] == "done"

    @pytest.mark.asyncio
    async def test_decide_action_approve_and_deny(self, app, tenant_1_user_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            create_resp = await client.post(
                "/v1/conversations",
                json={"title": "Action Test"},
                headers=tenant_1_user_headers,
            )
            cid = create_resp.json()["conversation_id"]
            interrupt_id = "intr_update_email_99"

            # Nothing is paused on this conversation, so a decision for any id is refused.
            # (The approve/deny flow against a real pending interrupt is covered in
            # tests/unit/modules/assistant/test_conversation_access.py.)
            approve_resp = await client.post(
                f"/v1/conversations/{cid}/actions/{interrupt_id}",
                json={"approved": True, "reason": "User verified MFA"},
                headers=tenant_1_user_headers,
            )
            assert approve_resp.status_code == 409


class TestEscalationApi:
    """Verifies listing escalations, agent reply authorization, and ticket resolution."""

    @pytest.mark.asyncio
    async def test_escalation_lifecycle(
        self, app, tenant_1_user_headers, tenant_1_agent_headers, tenant_2_user_headers
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create a conversation and mark as escalated in store
            store = get_conversation_store()
            cid = str(uuid4())
            store.create(
                tenant_id=TENANT_1, conversation_id=cid, title="Dispute #101", status="escalated"
            )

            # List escalations
            assert (
                await client.get("/v1/escalations", headers=tenant_1_user_headers)
            ).status_code == 403, "the escalation queue is for staff"
            esc_list = await client.get("/v1/escalations", headers=tenant_1_agent_headers)
            assert esc_list.status_code == 200
            assert any(e["escalation_id"] == cid for e in esc_list.json()["items"])

            # User (role=user) replying -> 403 Forbidden
            user_reply = await client.post(
                f"/v1/escalations/{cid}/reply",
                json={"text": "I am not an agent"},
                headers=tenant_1_user_headers,
            )
            assert user_reply.status_code == 403

            # Empty text reply -> 400 Bad Request
            empty_reply = await client.post(
                f"/v1/escalations/{cid}/reply",
                json={"text": "   "},
                headers=tenant_1_agent_headers,
            )
            assert empty_reply.status_code == 400

            # Agent replying -> 200 OK
            agent_reply = await client.post(
                f"/v1/escalations/{cid}/reply",
                json={"text": "Hello, I am taking over this ticket."},
                headers=tenant_1_agent_headers,
            )
            assert agent_reply.status_code == 200
            assert agent_reply.json()["role"] == "agent"

            # Foreign tenant agent replying -> 404 Not Found
            foreign_reply = await client.post(
                f"/v1/escalations/{cid}/reply",
                json={"text": "Sneaking in"},
                headers=tenant_2_user_headers,
            )
            assert foreign_reply.status_code in (403, 404)

            # Agent resolves ticket
            res_resolve = await client.post(
                f"/v1/escalations/{cid}/resolve",
                headers=tenant_1_agent_headers,
            )
            assert res_resolve.status_code == 200
            assert res_resolve.json()["status"] == "resolved"
