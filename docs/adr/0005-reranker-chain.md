# ADR 0005: Toggleable Reranker Chain with CPU/GPU Graceful Fallback

## Context & Problem
Re-ranking retrieved candidates via Cross-Encoders improves Top-$K$ retrieval precision but requires PyTorch and GPU acceleration. In resource-constrained or CPU-only container deployments, heavy Cross-Encoder models induce unacceptable response latency.

## Decision
We implement a **Unified Reranker Chain** through Answer.AI's `rerankers` library configured via `RERANKER_CHAIN` (`cross_encoder,flashrank,none`):
1. On GPU-accelerated nodes (e.g. RTX 3060), local Cross-Encoders (e.g. `BAAI/bge-reranker-v2-m3`) execute with high throughput.
2. If PyTorch or GPU acceleration is absent, or if the Cross-Encoder exceeds `RERANK_TIMEOUT_MS`, the chain gracefully cascades to FlashRank (lightweight ONNX runtime on CPU).
3. If FlashRank fails or is disabled, the system defaults to Reciprocal Rank Fusion (RRF) order.

All CPU/GPU inference is offloaded via `asyncio.to_thread` to protect FastAPI's event loop.

## Consequences
- **Positive:** High relevance retrieval with zero risk of complete pipeline failure across heterogeneous hardware environments.

