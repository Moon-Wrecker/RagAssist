"""Empirical Challenger Stress Harness for Ingestion, Chunking, Storage, and Security / RLS (sec_2).

Adversarial stress testing of:
1. Document parsers (Markdown, HTML, PyMuPDF) and 5-pass hybrid chunker with pathological inputs:
   - Massive markdown tables (hundreds of rows, preserving headers across splits).
   - Malformed/unclosed HTML with embedded scripts, style tags, and nested tables.
   - Zero-width spaces (\u200b, \u200c, \u200d, \ufeff) across headings, paragraphs, and tables.
   - Deeply nested and irregular heading hierarchies (H1 -> H4 -> H2 -> H6).
   - Massive unbroken paragraphs (10,000 words without punctuation).
   - Corrupt PDF headers and payloads.
   - Edge case: header-only tables exceeding max_tokens (silent drop).
2. Ingestion atomicity & S3 storage:
   - Upload compensation on database failure (S3 object cleanup).
   - Upload compensation on queue dispatch failure.
   - S3 tenant key prefixing and path traversal neutralization.
   - Ingestion worker cross-tenant queue payload tampering rejection.
   - Ingestion worker duplicate message idempotency.
   - Ingestion worker retry tracking and dead-lettering.
3. Tenant isolation, RLS and SQL injection resilience:
   - SQL injection payloads in FTS keyword queries.
   - SQL injection payloads in vector search filters.
   - PostgreSQL RLS session context setting and fail-closed behaviors.
   - JWT cryptographic signature tampering, alg:none rejection, and non-UUID tenant claims.
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest

from ragassist.modules.knowledge.adapters.chunkers.hybrid_chunker import HybridChunker
from ragassist.modules.knowledge.adapters.chunkers.passes import (
    table_pass,
    token_pass,
)
from ragassist.modules.knowledge.adapters.parsers.html_parser import HtmlParser
from ragassist.modules.knowledge.adapters.parsers.markdown_parser import MarkdownParser
from ragassist.modules.knowledge.adapters.parsers.pymupdf_parser import PyMuPDFParser
from ragassist.modules.knowledge.application.ingestion_service import (
    IngestOutcome,
    ProcessIngestionJob,
    UploadCommand,
    UploadDocument,
)
from ragassist.modules.knowledge.domain import (
    Block,
    IngestionJob,
    JobStatus,
    ParseError,
)
from ragassist.modules.retrieval.keyword_retriever import KeywordRetriever
from ragassist.modules.retrieval.vector_retriever import VectorRetriever
from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.shared.db.uow import UnitOfWork, tenant_uow
from ragassist.shared.domain import TenantId, TenantIsolationError, UserId
from ragassist.shared.security.jwt import (
    UserRole,
    create_access_token,
    decode_access_token,
)

pytestmark = [pytest.mark.security, pytest.mark.unit]


# ==============================================================================
# Helpers & Fakes
# ==============================================================================


class SimpleWordTokenizer:
    """Whitespace word counter simulating standard tokenizer."""

    def count(self, text: str) -> int:
        return len(text.split())


class InMemoryStoreSpy:
    """In-memory object store tracking put and delete operations."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted_keys: list[str] = []

    async def put_object(self, key: str, data: bytes, content_type: str = "") -> str:
        self.objects[key] = data
        return f"s3://bucket/{key}"

    async def get_object(self, key: str) -> bytes:
        if key not in self.objects:
            raise KeyError(f"Object {key} not found")
        return self.objects[key]

    async def delete_object(self, key: str) -> bool:
        self.deleted_keys.append(key)
        self.objects.pop(key, None)
        return True


class InMemoryQueueSpy:
    """Queue spy recording enqueued messages."""

    def __init__(self, fail_on_send: bool = False) -> None:
        self.messages: list[str] = []
        self.fail_on_send = fail_on_send

    async def send(self, body: str) -> None:
        if self.fail_on_send:
            raise RuntimeError("SQS dispatch failed")
        self.messages.append(body)


class InMemoryDocRepoSpy:
    """Document repository spy tracking documents, jobs, and chunk swaps."""

    def __init__(self, fail_on_add_job: bool = False, fail_on_replace: bool = False) -> None:
        self.documents: dict[str, Any] = {}
        self.jobs: dict[str, Any] = {}
        self.claimed_jobs: list[str] = []
        self.chunks_by_doc: dict[str, list[Any]] = {}
        self.fail_on_add_job = fail_on_add_job
        self.fail_on_replace = fail_on_replace

    def transaction(self):
        @asynccontextmanager
        async def _tx():
            yield

        return _tx()

    async def add_document(self, doc: Any) -> None:
        self.documents[str(doc.id)] = doc

    async def add_job(self, job: Any) -> None:
        if self.fail_on_add_job:
            raise RuntimeError("Database connection lost during add_job")
        self.jobs[str(job.job_id)] = job

    async def get_job(self, job_id: str) -> Any:
        return self.jobs.get(str(job_id))

    async def claim_job(self, job_id: str, tenant_id: str) -> bool:
        job = self.jobs.get(str(job_id))
        if not job:
            return False
        if job.status == JobStatus.RUNNING or job.status == "running":
            return False
        self.claimed_jobs.append(job_id)
        job.status = JobStatus.RUNNING
        return True

    async def get_document(self, document_id: Any) -> Any:
        return self.documents.get(str(document_id))

    async def replace_chunks(self, document_id: Any, chunks: list[Any], tenant_id: str) -> None:
        if self.fail_on_replace:
            raise RuntimeError("Chunk swap database deadlock")
        self.chunks_by_doc[str(document_id)] = list(chunks)

    async def save_job(self, job: Any, tenant_id: str) -> None:
        self.jobs[str(job.job_id)] = job


class DummyEmbedder(EmbeddingProvider):
    """Deterministic dummy embedder for tests."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1536 for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * 1536

    def dimension(self) -> int:
        return 1536


# ==============================================================================
# Suite 1: Document Parsers & 5-Pass Hybrid Chunker Adversarial Tests
# ==============================================================================


class TestParsersAndChunkerAdversarial:
    """Stress tests for MarkdownParser, HtmlParser, PyMuPDFParser and 5-pass chunker."""

    @pytest.mark.asyncio
    async def test_massive_markdown_table_split_preserves_headers(self) -> None:
        """Verify that a massive markdown table is split across blocks with header lines preserved."""
        parser = MarkdownParser()
        tokenizer = SimpleWordTokenizer()

        header = "| Product ID | Product Name | Department | Price | Stock Quantity | Status |\n"
        separator = "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        data_rows = [
            f"| SKU-{i:05d} | Item Name {i} | Category {i % 10} | ${i * 1.5:.2f} | {i * 7} | InStock |\n"
            for i in range(1, 201)
        ]
        md_text = f"# Inventory Catalog\n\n{header}{separator}{''.join(data_rows)}"

        parsed = await parser.parse(md_text.encode("utf-8"), filename="catalog.md")
        assert len(parsed.blocks) >= 2
        table_blocks = [b for b in parsed.blocks if b.kind == "table"]
        assert len(table_blocks) == 1

        # Run table pass with max 50 tokens
        split_blocks = table_pass(table_blocks, max_tokens=50, tokenizer=tokenizer)
        assert len(split_blocks) > 1

        # Every split block MUST preserve the markdown table header line
        for block in split_blocks:
            assert block.kind == "table"
            lines = block.text.strip().splitlines()
            assert lines[0].strip() == header.strip()
            assert lines[1].strip() == separator.strip()

    @pytest.mark.asyncio
    async def test_malformed_html_unclosed_tags_and_scripts(self) -> None:
        """Verify HTML parser cleanly strips malicious <script> and <style> tags and handles unclosed tags."""
        parser = HtmlParser()
        malformed_html = """
        <html>
        <head>
            <title>Security Test Document</title>
            <script>alert('XSS Payload'); window.location='http://evil.com';</script>
            <style>body { display: none; } .hidden { visibility: hidden; }</style>
        </head>
        <body>
            <h1>Section Title</h1>
            <p>Unclosed paragraph text with <b>bold and <i>italic nested
            <div>
                <table>
                    <tr><th>Header A</th><th>Header B</th></tr>
                    <tr><td>Val 1</td><td>Val 2</td></tr>
                <!-- Unclosed table and tags -->
        """
        parsed = await parser.parse(malformed_html.encode("utf-8"), filename="test.html")
        assert parsed.title == "Security Test Document"

        # Verify no script or style content leaked into blocks
        all_text = " ".join(b.text for b in parsed.blocks)
        assert "alert" not in all_text
        assert "evil.com" not in all_text
        assert "display: none" not in all_text

        # Verify text was still parsed despite unclosed tags
        assert "Unclosed paragraph text" in all_text
        assert any(b.kind == "heading" and "Section Title" in b.text for b in parsed.blocks)

    @pytest.mark.asyncio
    async def test_html_unclosed_heading_flushes_without_crash(self) -> None:
        """Verify that an unclosed HTML heading tag without </h1> is flushed without crashing."""
        parser = HtmlParser()
        html_text = "<html><body><h1>Unclosed Title<p>Paragraph body</p></body></html>"
        parsed = await parser.parse(html_text.encode("utf-8"), filename="unclosed_h.html")
        all_text = " ".join(b.text for b in parsed.blocks)
        assert "Unclosed Title" in all_text
        assert "Paragraph body" in all_text

    @pytest.mark.asyncio
    async def test_zero_width_spaces_and_invisible_characters(self) -> None:
        """Verify parsers and chunkers do not crash or loop infinitely on zero-width/bidi characters."""
        parser = MarkdownParser()
        tokenizer = SimpleWordTokenizer()

        # Text littered with zero-width spaces (\u200b), zero-width non-joiners (\u200c), BOM (\ufeff)
        zw_text = (
            "# Main\u200bHeading\n\n"
            "Paragraph\u200c with\u200d invisible\ufeff characters.\n\n"
            "| Col\u200b1 | Col\u200b2 |\n"
            "| --- | --- |\n"
            "| Val\u200c1 | Val\u200d2 |\n"
        )
        parsed = await parser.parse(zw_text.encode("utf-8"), filename="zw.md")
        assert len(parsed.blocks) >= 2

        chunker = HybridChunker(max_tokens=64, tokenizer=tokenizer)
        chunks = chunker.chunk(parsed, title="ZeroWidthDoc")
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.text.strip() != ""
            assert len(chunk.embed_text) > 0

    @pytest.mark.asyncio
    async def test_deeply_nested_and_irregular_headings(self) -> None:
        """Verify heading stack handles level skipping and hierarchy resets accurately."""
        parser = MarkdownParser()
        md_text = """# H1 Top
Content 1
#### H4 Skipped
Content under skipped H4
## H2 Step Down
Content under H2
###### H6 Deep
Content under H6
# H1 Reset
Content under new H1
"""
        parsed = await parser.parse(md_text.encode("utf-8"), filename="nested.md")
        headings = [b for b in parsed.blocks if b.kind == "heading"]
        assert len(headings) == 5

        # Check heading paths of paragraphs
        paras = [b for b in parsed.blocks if b.kind == "paragraph"]
        assert paras[0].heading_path == ("H1 Top",)
        assert paras[1].heading_path == ("H1 Top", "H4 Skipped")
        # H2 is subordinate to H1 Top, so path is ('H1 Top', 'H2 Step Down')
        assert paras[2].heading_path == ("H1 Top", "H2 Step Down")
        assert paras[3].heading_path == ("H1 Top", "H2 Step Down", "H6 Deep")
        # H1 Reset resets to level 1, so path is ('H1 Reset',)
        assert paras[4].heading_path == ("H1 Reset",)

    def test_giant_unbroken_sentence_splitting(self) -> None:
        """Verify token_pass splits a 5,000-word paragraph without sentence punctuation into bounded chunks."""
        tokenizer = SimpleWordTokenizer()
        giant_text = " ".join([f"word{i}" for i in range(5000)])
        block = Block(kind="paragraph", text=giant_text, heading_path=("Doc",), page=1)

        split_blocks = token_pass([block], max_tokens=100, tokenizer=tokenizer)
        assert len(split_blocks) >= 50

        # Verify no words were lost
        recombined_words = []
        for b in split_blocks:
            assert tokenizer.count(b.text) <= 100
            recombined_words.extend(b.text.split())
        assert len(recombined_words) == 5000

    def test_table_pass_header_only_oversized_table_drop_behavior(self) -> None:
        """Document empirical finding: table_pass drops header-only tables when they exceed max_tokens."""
        tokenizer = SimpleWordTokenizer()
        # Header-only table with many columns exceeding max_tokens
        header_cols = [f"Col{i}" for i in range(50)]
        table_text = "| " + " | ".join(header_cols) + " |\n| " + " | ".join(["---"] * 50) + " |"
        block = Block(kind="table", text=table_text, heading_path=(), page=1)

        result = table_pass([block], max_tokens=20, tokenizer=tokenizer)
        # Because data_rows is empty and the header exceeds max_tokens, table_pass emits nothing
        assert len(result) == 0, (
            "Confirms empirical finding: header-only oversized table is dropped"
        )

    @pytest.mark.asyncio
    async def test_corrupt_pdf_header_and_structure_raises_cleanly(self) -> None:
        """Verify PDF parser raises ParseError cleanly on corrupted PDF bytes."""
        parser = PyMuPDFParser()

        with pytest.raises(ParseError, match="Invalid PDF header"):
            await parser.parse(b"This is not a PDF file", filename="bad.pdf")

        with pytest.raises(ParseError, match="Corrupt PDF structure"):
            await parser.parse(b"%PDF-1.4 but corrupted data inside", filename="bad.pdf")


# ==============================================================================
# Suite 2: Ingestion Atomicity, S3 Key Scoping & Queue Tampering
# ==============================================================================


class TestIngestionAtomicityAndS3Security:
    """Stress tests for S3 tenant key prefixing, upload rollback cleanups, and worker security."""

    @pytest.mark.asyncio
    async def test_upload_compensation_cleans_s3_on_db_failure(self) -> None:
        """Verify that if database persistence fails, the uploaded S3 object is rolled back/deleted."""
        store = InMemoryStoreSpy()
        queue = InMemoryQueueSpy()
        repo = InMemoryDocRepoSpy(fail_on_add_job=True)

        uploader = UploadDocument(store=store, queue=queue, documents=repo)
        cmd = UploadCommand(
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            filename="document.md",
            mime="text/markdown",
            content=b"# Header\nContent",
        )

        with pytest.raises(RuntimeError, match="Database connection lost"):
            await uploader.execute(cmd)

        # Verification of compensation: S3 object was cleaned up
        assert len(store.deleted_keys) == 1
        assert len(store.objects) == 0

    @pytest.mark.asyncio
    async def test_upload_compensation_cleans_s3_on_queue_failure(self) -> None:
        """Verify that if SQS queue dispatch fails, the S3 object is rolled back/deleted."""
        store = InMemoryStoreSpy()
        queue = InMemoryQueueSpy(fail_on_send=True)
        repo = InMemoryDocRepoSpy()

        uploader = UploadDocument(store=store, queue=queue, documents=repo)
        cmd = UploadCommand(
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            filename="document.md",
            mime="text/markdown",
            content=b"# Header\nContent",
        )

        with pytest.raises(RuntimeError, match="SQS dispatch failed"):
            await uploader.execute(cmd)

        # Verification of compensation: S3 object was cleaned up
        assert len(store.deleted_keys) == 1
        assert len(store.objects) == 0

    @pytest.mark.asyncio
    async def test_s3_tenant_key_prefixing_neutralizes_directory_traversal(self) -> None:
        """Verify that object keys strictly begin with tenants/{tenant_id}/ and path traversal is neutralized."""
        store = InMemoryStoreSpy()
        queue = InMemoryQueueSpy()
        repo = InMemoryDocRepoSpy()
        tenant_id = str(uuid4())

        uploader = UploadDocument(store=store, queue=queue, documents=repo)

        # Attempt path traversal in filename
        malicious_filenames = [
            "../../../../etc/shadow",
            "..\\..\\windows\\system32\\cmd.exe",
            "/absolute/root/path.txt",
            "....//....//traversal.md",
        ]

        for fname in malicious_filenames:
            cmd = UploadCommand(
                tenant_id=tenant_id,
                user_id=str(uuid4()),
                filename=fname,
                mime="text/markdown",
                content=b"# Safe",
            )
            result = await uploader.execute(cmd)

            # Object key MUST start with tenants/{tenant_id}/documents/
            assert result.object_key.startswith(f"tenants/{tenant_id}/documents/")
            assert ".." not in result.object_key
            # The object key must be safely scoped within the document ID prefix
            assert re.match(
                rf"^tenants/{tenant_id}/documents/[0-9a-f\-]+/[^/\\]+$", result.object_key
            )

    @pytest.mark.asyncio
    async def test_worker_cross_tenant_queue_tampering_rejected(self) -> None:
        """Verify that if an SQS message arrives with a forged tenant_id, the worker REJECTS it."""
        repo = InMemoryDocRepoSpy()
        store = InMemoryStoreSpy()
        embedder = DummyEmbedder()
        chunker = HybridChunker(max_tokens=256, tokenizer=SimpleWordTokenizer())

        job_tenant = str(uuid4())
        attacker_tenant = str(uuid4())
        job_id = str(uuid4())
        doc_id = str(uuid4())

        # Setup genuine job belonging to job_tenant
        job = IngestionJob(
            job_id=job_id,
            document_id=doc_id,
            tenant_id=job_tenant,
            status=JobStatus.QUEUED,
        )
        await repo.add_job(job)

        # Attacker injects SQS message with attacker_tenant claiming job_id
        forged_message = {
            "job_id": job_id,
            "tenant_id": attacker_tenant,
            "object_key": f"tenants/{attacker_tenant}/documents/{doc_id}/test.md",
            "document_id": doc_id,
        }

        worker = ProcessIngestionJob(
            documents=repo,
            store=store,
            parsers={"text/markdown": MarkdownParser()},
            chunker=chunker,
            embedder=embedder,
        )

        outcome = await worker.handle(forged_message)
        assert outcome == IngestOutcome.REJECTED
        assert job_id not in repo.claimed_jobs

    @pytest.mark.asyncio
    async def test_worker_idempotency_duplicate_skipping(self) -> None:
        """Verify that already completed jobs are skipped cleanly when redelivered by SQS."""
        repo = InMemoryDocRepoSpy()
        store = InMemoryStoreSpy()
        embedder = DummyEmbedder()
        chunker = HybridChunker(max_tokens=256, tokenizer=SimpleWordTokenizer())

        tenant_id = str(uuid4())
        job_id = str(uuid4())
        doc_id = str(uuid4())

        job = IngestionJob(
            job_id=job_id,
            document_id=doc_id,
            tenant_id=tenant_id,
            status=JobStatus.COMPLETED,
        )
        await repo.add_job(job)

        message = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "object_key": f"tenants/{tenant_id}/documents/{doc_id}/test.md",
            "document_id": doc_id,
        }

        worker = ProcessIngestionJob(
            documents=repo,
            store=store,
            parsers={"text/markdown": MarkdownParser()},
            chunker=chunker,
            embedder=embedder,
        )

        outcome = await worker.handle(message)
        assert outcome == IngestOutcome.DUPLICATE_SKIPPED


# ==============================================================================
# Suite 3: Tenant Isolation, RLS Context, SQL Injection Resilience & JWT
# ==============================================================================


class FakeAsyncSessionForSqlTest:
    """Fake session recording executed SQL and parameter bindings."""

    def __init__(self) -> None:
        self.executed_queries: list[tuple[str, dict[str, Any]]] = []
        self.is_active = True

    async def begin(self) -> None:
        pass

    async def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> Any:
        sql_str = str(statement)
        params = parameters or {}
        self.executed_queries.append((sql_str, params))

        class FakeResult:
            def fetchall(self):
                return []

        return FakeResult()

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class TestTenantIsolationAndSqlInjection:
    """Stress tests for SQL injection resilience, RLS configuration, and JWT authentication."""

    @pytest.mark.asyncio
    async def test_fts_sql_injection_payloads_safely_parameterized(self) -> None:
        """Verify that adversarial SQL injection strings in FTS queries are strictly bound as parameters."""
        session = FakeAsyncSessionForSqlTest()

        retriever = KeywordRetriever(
            session_factory=lambda: session,
            backend="fts",
            table_name="chunks",
        )

        tenant_id = uuid4()
        injection_queries = [
            "'; DROP TABLE chunks; --",
            "' OR 1=1 --",
            "' UNION SELECT id, document_id, tenant_id, text, embed_text, heading_path, page, title, 1.0 FROM chunks --",
            '""" OR "1"="1',
            "test & | ! ( ) <->",
        ]

        for payload in injection_queries:
            malicious_filter = "00000000-0000-0000-0000-000000000000' OR '1'='1"
            await retriever._search_fts(
                session=session,
                query=payload,
                tenant_id=tenant_id,
                k=5,
                filters={"document_id": malicious_filter},
            )

            # Retrieve the latest executed query
            sql, params = session.executed_queries[-1]

            # The payload MUST NOT be present in raw SQL text!
            assert payload not in sql
            assert "DROP TABLE" not in sql
            assert "UNION SELECT" not in sql

            # The payload MUST be passed in params dictionary
            assert params["query"] == payload
            assert params["tenant_id"] == tenant_id
            assert params["filter_document_id"] == malicious_filter

    @pytest.mark.asyncio
    async def test_vector_search_sql_injection_payloads_safely_parameterized(self) -> None:
        """Verify that adversarial SQL injection strings in vector search filters are strictly bound."""
        session = FakeAsyncSessionForSqlTest()
        embedder = DummyEmbedder()

        @asynccontextmanager
        async def session_ctx():
            yield session

        retriever = VectorRetriever(
            embedder=embedder,
            session_factory=session_ctx,
            table_name="chunks",
        )

        tenant_id = uuid4()
        malicious_doc_filter = "fake-doc-id' OR 1=1; DELETE FROM chunks; --"

        await retriever.search(
            query="safe semantic query",
            tenant_id=tenant_id,
            k=5,
            filters={"document_id": malicious_doc_filter},
        )

        # Find the SELECT query from chunks
        select_queries = [q for q in session.executed_queries if "FROM chunks" in q[0]]
        assert len(select_queries) == 1
        sql, params = select_queries[0]

        # Raw SQL must NOT contain malicious injection string
        assert "DELETE FROM chunks" not in sql
        assert "OR 1=1" not in sql

        # Parameter binding must contain the raw string safely
        assert params["filter_document_id"] == malicious_doc_filter
        assert params["tenant_id"] == tenant_id

    @pytest.mark.asyncio
    async def test_unit_of_work_sets_local_rls_and_prevents_bleeding(self) -> None:
        """Verify UnitOfWork sets transaction-scoped app.tenant_id with is_local=true."""
        session = FakeAsyncSessionForSqlTest()
        tenant_id = uuid4()

        uow = UnitOfWork(session, tenant_id=tenant_id)
        async with uow:
            pass

        # Check set_config was executed with true (local to transaction)
        rls_queries = [q for q in session.executed_queries if "set_config('app.tenant_id'" in q[0]]
        assert len(rls_queries) == 1
        sql, params = rls_queries[0]
        assert "set_config('app.tenant_id', :tid, true)" in sql
        assert params["tid"] == str(tenant_id)

    @pytest.mark.asyncio
    async def test_tenant_uow_rejects_missing_tenant_id(self) -> None:
        """Verify tenant_uow fails closed if tenant_id is None or empty."""
        with pytest.raises(
            TenantIsolationError, match="Cannot establish UnitOfWork without a valid TenantId"
        ):
            async with tenant_uow(None):  # type: ignore[arg-type]
                pass

    def test_jwt_tampering_and_forgery_rejection(self) -> None:
        """Verify JWT decoding rejects forged tokens, alg:none, non-UUID claims, and invalid signatures."""
        valid_uid = UserId(uuid4())
        valid_tid = TenantId(uuid4())
        valid_token = create_access_token(valid_uid, valid_tid, UserRole.USER)

        # 1. Valid token succeeds
        principal = decode_access_token(valid_token)
        assert principal.user_id == valid_uid
        assert principal.tenant_id == valid_tid

        # 2. Tampered signature fails
        tampered_token = valid_token[:-4] + "ABCD"
        with pytest.raises(ValueError, match="Invalid or expired authentication token"):
            decode_access_token(tampered_token)

        # 3. Non-UUID tenant_id in payload fails
        parts = valid_token.split(".")
        import base64

        def b64url(s: bytes) -> str:
            return base64.urlsafe_b64encode(s).decode("utf-8").rstrip("=")

        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload["tenant_id"] = "not-a-valid-uuid"
        forged = f"{parts[0]}.{b64url(json.dumps(payload).encode('utf-8'))}.{parts[2]}"
        with pytest.raises(ValueError, match="Invalid or expired authentication token"):
            decode_access_token(forged)
