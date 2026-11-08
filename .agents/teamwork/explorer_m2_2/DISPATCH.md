# DISPATCH — explorer_m2_2

- **Role**: Hybrid Chunker Explorer
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_2
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md
- **Implementation Plan**: d:\Coding\RagAssist-1\docs\arc42\ or implementation_plan.md

## Objective
Investigate and design the 5-pass structure-aware `HybridChunker`:
1. Pass 1: AST Structural Splitting (Markdown headings `#`, `##`, `###`, paragraphs, lists, codeblocks, tables).
2. Pass 2: Table Protection (tables must not be split across chunks mid-row; large tables exceeding chunk size split by rows with repeated header rows).
3. Pass 3: Contextual Breadcrumb Enrichment (prepend hierarchical header paths like `Document > Section > Subsection` to chunk content and chunk metadata `heading_path`).
4. Pass 4: Token Budgeting & Chunk Size Bounds (target ~512 tokens with configurable overlap; using tokenizer/tiktoken safely).
5. Pass 5: Sibling Merging (merge adjacent short chunks under the same header without exceeding token limit).
6. Async/sync separation: ensure all CPU-heavy tokenization and chunking runs in `run_cpu_bound()` from `ragassist.shared.resilience`.
7. Design unit test matrix for `tests/unit/test_chunker.py`.

Deliver technical analysis to `analysis_chunking.md` and summary in `handoff.md`.


## 2026-11-08T09:01:46Z
You are explorer_m2_2 (Hybrid Chunker Explorer) for Milestone 2 (Ingestion & Knowledge Storage Pipeline) in project RagAssist.

CRITICAL INSTRUCTIONS:
1. You MUST read the original user request at:
   `d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md`
   before beginning work.
2. Read `d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md`, `d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md`, and `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_2\DISPATCH.md`.
3. Check existing codebase, especially:
   - `src/ragassist/modules/knowledge/`
   - `src/ragassist/shared/resilience.py` (run_cpu_bound)
   - `src/ragassist/shared/config/settings.py` (CHUNK_SIZE, CHUNK_OVERLAP, etc.)
   - pyproject.toml dependencies (tiktoken, etc.).
4. You are a READ-ONLY explorer. DO NOT write or edit source code or test files. Only write your analysis and handoff report inside your state folder:
   `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_2\`
5. In your analysis:
   - Detail the 5-pass structure-aware `HybridChunker` implementation:
     - Pass 1: AST Structural Splitting (Markdown headings `#`, `##`, `###`, paragraphs, lists, codeblocks, tables).
     - Pass 2: Table Protection (tables must not be split across chunks mid-row; if a large table exceeds chunk size, split by rows with repeated header rows prepended).
     - Pass 3: Contextual Breadcrumb Enrichment (prepend hierarchical header paths like `Document > Section > Subsection` to chunk content and chunk metadata `heading_path`).
     - Pass 4: Token Budgeting & Chunk Size Bounds (target ~512 tokens with configurable overlap; using tokenizer/tiktoken safely).
     - Pass 5: Sibling Merging (merge adjacent short chunks under the same header without exceeding token limit).
   - Detail chunk representation (`Chunk` DTO with `content`, `heading_path`, `page_number`, `token_count`, `chunk_index`, `metadata`).
   - Specify how CPU-bound tokenization and chunking operations are offloaded using `run_cpu_bound()`.
   - Propose the exact file paths and interfaces adhering to the Modular Monolith architecture in `PROJECT.md`.
   - Provide a comprehensive test specification for `tests/unit/test_chunker.py`.
6. Write your detailed analysis to `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_2\analysis_chunking.md` and complete handoff report to `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_2\handoff.md`.
7. Once finished, send a message back to the orchestrator summarizing your findings and linking to your reports.
