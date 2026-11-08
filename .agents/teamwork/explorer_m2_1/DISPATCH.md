# DISPATCH — explorer_m2_1

- **Role**: Document Parsers Explorer
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_1
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md
- **Implementation Plan**: d:\Coding\RagAssist-1\docs\arc42\ or implementation_plan.md

## Objective
Investigate and design the document AST parsers for the Knowledge ingestion module:
1. Multi-format support: PDF, HTML, Markdown, and PlainText.
2. PDF parsing with PyMuPDF4LLM: table structure extraction, markdown formatting, page numbers, layout preservation.
3. HTML parsing with markdownify: clean markdown conversion preserving headings and tables.
4. Error handling: corrupt files, empty files, password-protected PDFs, non-UTF8 text.
5. Async/sync separation: ensure all CPU-heavy parsing runs in `run_cpu_bound()` from `ragassist.shared.resilience`.
6. Design unit test matrix for `tests/unit/test_parsers.py`.

Deliver technical analysis to `analysis_parsers.md` and summary in `handoff.md`.


## 2026-11-08T09:01:38Z
You are explorer_m2_1 (Document Parsers Explorer) for Milestone 2 (Ingestion & Knowledge Storage Pipeline) in project RagAssist.

CRITICAL INSTRUCTIONS:
1. You MUST read the original user request at:
   `d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md`
   before beginning work.
2. Read `d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md`, `d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md`, and `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_1\DISPATCH.md`.
3. Check existing codebase, especially:
   - `src/ragassist/modules/knowledge/`
   - `src/ragassist/shared/resilience.py` (run_cpu_bound)
   - `src/ragassist/shared/config/settings.py`
   - `tests/unit/test_parsers.py` (if any) or existing test fixtures.
   - pyproject.toml dependencies (PyMuPDF4LLM / fitz, markdownify).
4. You are a READ-ONLY explorer. DO NOT write or edit source code or test files. Only write your analysis and handoff report inside your state folder:
   `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_1\`
5. In your analysis:
   - Detail the architecture and interfaces for AST document parsers (`PDFParser`, `HTMLParser`, `MarkdownParser`, `PlainTextParser`).
   - Define the Document AST Node data structures (e.g., `DocumentNode`, `HeadingNode`, `TableNode`, `ParagraphNode`, with metadata like `page_number`, `bounding_box`, `is_table`).
   - Specify how `PyMuPDF4LLM` extracts tables as Markdown tables while preserving page number references.
   - Specify how `markdownify` strips script/style tags and preserves headings `#` and tables `<table>` cleanly.
   - Specify edge-case handling: corrupted PDFs, password-protected PDFs, empty files, non-UTF-8 encodings, massive files (>50MB).
   - Specify how CPU-bound parsing operations are offloaded using `run_cpu_bound()`.
   - Propose the exact file paths and interfaces adhering to the Modular Monolith architecture in `PROJECT.md`.
   - Provide a comprehensive test specification for `tests/unit/test_parsers.py`.
6. Write your detailed analysis to `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_1\analysis_parsers.md` and complete handoff report to `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_1\handoff.md`.
7. Once finished, send a message back to the orchestrator summarizing your findings and linking to your reports.
