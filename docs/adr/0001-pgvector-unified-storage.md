# ADR 0001: PostgreSQL + pgvector for Unified Multi-Tenant Storage & Checkpoints

## Context & Problem
We require a scalable vector store capable of handling high-dimensional embeddings while strictly guaranteeing tenant-level data isolation, transactional consistency, conversation memory checkpoints, and audit trails without unnecessary multi-database complexity.

## Decision
We select **PostgreSQL 16 with the `pgvector` extension** as our unified data store for:
1. Document metadata, parsed chunks, and embedding vectors.
2. Relational tenant, user, audit log, and escalation records.
3. LangGraph conversation state persistence via `langgraph-checkpoint-postgres`.
4. Multi-tenant isolation enforced directly at the database engine level via PostgreSQL Row-Level Security (RLS).

## Consequences
- **Positive:** Single ACID-compliant database with zero synchronization lag between relational tables and vector indices.
- **Positive:** pgvector ≥ 0.8 `iterative_scan` handles filtered HNSW queries without recall degradation.
- **Negative:** For ultra-large scale corpora (hundreds of millions of vectors), specialized distributed vector databases (like Qdrant) might offer higher indexing throughput. However, for a production-grade multi-tenant SaaS assistant, Postgres + pgvector reduces operational complexity substantially.

