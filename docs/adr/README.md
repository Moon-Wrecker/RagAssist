# ==============================================================================
# RagAssist Architecture Decision Records (ADRs)
# ==============================================================================

This directory contains lightweight Architecture Decision Records documenting key architectural, security, and algorithmic choices in **RagAssist**:

- [0001: PostgreSQL + pgvector for Unified Multi-Tenant Storage & Checkpoints](file:///d:/Coding/RagAssist-1/docs/adr/0001-pgvector-unified-storage.md)
- [0002: Row-Level Security (RLS) and Transactional Context Isolation](file:///d:/Coding/RagAssist-1/docs/adr/0002-row-level-security.md)
- [0003: Structure-Aware 5-Pass Hybrid Chunking](file:///d:/Coding/RagAssist-1/docs/adr/0003-hybrid-chunking.md)
- [0004: Decision Layer First with Calibrated Probabilities](file:///d:/Coding/RagAssist-1/docs/adr/0004-decision-layer.md)
- [0005: Toggleable Reranker Chain with CPU/GPU Graceful Fallback](file:///d:/Coding/RagAssist-1/docs/adr/0005-reranker-chain.md)
- [0006: Per-User Conversation Access and Approval Bound to the Pending Action](file:///d:/Coding/RagAssist-1/docs/adr/0006-conversation-access-and-approval-binding.md)
- [0007: Accounts, Passwords, Refresh Sessions and Invite Links](0007-accounts-and-sessions.md)
- [0008: Live Events over LISTEN/NOTIFY, Human Handoff and Turns That Outlive the Request](0008-live-events-handoff-and-detached-turns.md)
- [0009: Web App: Same-Origin SPA, In-Memory Access Token and a Glass Design System](0009-web-app.md)
- [0012: Langfuse Tracing of Assistant Turns, with Redaction Before Export](0012-langfuse-tracing.md)
- [0010: Chat UI: a Pure Stream Reducer, Sanitised Markdown and Inline Approval](0010-chat-ui.md)
- [0011: Admin Screens: Inbox, Knowledge Base and Team](0011-admin-screens.md)
- [0013: Google Gemini as a First-Class Chat Provider](0013-gemini-provider.md)
- [0014: Web Delivery: Built SPA on Unprivileged nginx, Same Origin as the API](0014-web-delivery.md)
