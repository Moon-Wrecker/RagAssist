# DISPATCH — worker_m3

- **Role**: Milestone 3 Implementer (Hybrid Retrieval & Toggleable Reranker Engine)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\worker_m3
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md

## Exclusive Write Ownership
You have exclusive write ownership over:
- `src/ragassist/platform/rerank/` (Reranker protocols and adapters)
- `src/ragassist/modules/retrieval/` (Retrieval protocols, dense search, sparse search, RRF fusion, retrieval service)
- `tests/unit/test_retrieval.py`
- `tests/unit/test_reranker.py`

DO NOT modify files outside your write ownership (e.g., `platform/storage/`, `platform/queue/`, `modules/knowledge/`, `modules/actions/`, `modules/assistant/`).

## Task Instructions
1. Implement Reranker Protocols and Adapters in `src/ragassist/platform/rerank/`:
   - `Reranker` protocol in `ports.py`.
   - `CrossEncoderReranker` using `sentence-transformers` (`BAAI/bge-reranker-v2-m3`), offloading GPU/CPU inference to `run_cpu_bound()` from `ragassist.shared.resilience`.
   - `FlashRankReranker` using `flashrank` (CPU ONNX), offloaded to `run_cpu_bound()`.
   - `NoOpReranker` returning candidate ordering unchanged.
   - Configurable `RerankerChain` fallback (GPU Cross-Encoder -> CPU FlashRank -> NoOp) adhering to `AGENTS.md § 2.3`.
2. Implement Hybrid Retrieval Components in `src/ragassist/modules/retrieval/`:
   - `DenseRetriever`: pgvector cosine search using `relaxed_order` HNSW index with RLS `tenant_id` session context.
   - `SparseRetriever`: PostgreSQL Full-Text Search (FTS) using `tsvector` and `websearch_to_tsquery` for exact keyword and symbol matches.
   - `ReciprocalRankFusion` (RRF): Combines dense and sparse ranked candidate lists using score formula:
     $$\text{RRF}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{k + \text{rank}_m(d)}$$ with constant $k = 60$.
   - `HybridRetrievalService`: End-to-end service coordinating dense retrieval, sparse retrieval, RRF candidate combination, and toggleable reranking to return top-k `RetrievedChunk` items.
3. Write comprehensive unit tests in `tests/unit/test_retrieval.py` and `tests/unit/test_reranker.py`. Run tests using `BypassSandbox=True` on Windows.
4. Write `changes.md` and `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\worker_m3\`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.


## 2026-11-08T09:04:29Z
You are worker_m3 (Milestone 3 Implementer: Hybrid Retrieval & Toggleable Reranker Engine) for project RagAssist.
All dispatch requirements and write boundaries received.
