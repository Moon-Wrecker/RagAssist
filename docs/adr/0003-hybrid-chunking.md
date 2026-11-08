# ADR 0003: Structure-Aware 5-Pass Hybrid Chunking

## Context & Problem
Naive character or token splitters sever tables across row boundaries, strip away heading context, and detach list items from their headers. Conversely, purely structural chunking can produce oversized chunks that exceed embedding token budgets or tiny chunks that lack standalone semantic context.

## Decision
We implement a **5-Pass Hybrid Chunking** algorithm (`HybridChunker`):
1. **Structure Pass:** Parse document hierarchy (AST) into discrete semantic blocks (sections, paragraphs, tables, code blocks) retaining heading ancestry paths.
2. **Token Pass:** Split oversized blocks exceeding `CHUNK_MAX_TOKENS` at natural linguistic boundaries (sentences/clauses) using the model's exact tokenizer.
3. **Merge Pass:** Merge adjacent undersized sibling blocks residing under the same heading up to `CHUNK_MAX_TOKENS`.
4. **Table Protection Pass:** Preserve complete markdown tables where possible; if oversized, split by rows while repeating the header row on each partition.
5. **Contextual Header Pass:** Prepend document title and section breadcrumbs (`[Document: ... | Section: ...]`) to the embedded text while storing pristine original text for citation rendering.

## Consequences
- **Positive:** High retrieval precision, zero broken tables, and preserved semantic grounding.
- **Positive:** Provenance tracking (page numbers, heading paths) enables exact citations in generated answers.

