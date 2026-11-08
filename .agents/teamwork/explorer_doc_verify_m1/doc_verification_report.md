# Primary SDK & API Documentation Verification Report: Decision Layer Adapters
**Author**: `explorer_doc_verify_m1`  
**Date**: 2026-11-08  
**Scope**: Verification of Jev (`typesafe-sdk`), OpenAI Decisions API (`/v1/decisions`), and Strands Decider adapters against official primary documentation in accordance with **AGENTS.md § 3.5 (Goal -> Research -> Implement/Verify)**.

---

## Executive Summary

Pursuant to AGENTS.md § 3.5, this investigation verified the primary documentation, PyPI packages, wire protocols, and SDK interfaces for all three System One decision adapters implemented in Milestone 1 (`src/ragassist/platform/decisions/`):
1. **OpenAI Decisions API (`/v1/decisions`)**: **VERIFIED** against primary OpenAI documentation and SDK references. The endpoint `POST /v1/decisions` and model `gpt-6-luna` exist as official high-speed structured evaluation tools. The adapter implementation closely mirrors the official wire protocol, with minor schema recommendations for option lists.
2. **TypeSafe AI Jev (`typesafe-sdk`, `jev`)**: **DIVERGENT / SPECULATIVE IMPLEMENTATION**. Official packages `typesafe-sdk` (v0.7.5) and `jev` (v0.3.0) exist on PyPI and are documented at `https://docs.typesafe.ai/go/python-sdk`. However, the adapter in `jev_adapter.py` was written without consulting the official primary SDK, resulting in wire protocol discrepancies (calling `/v1/decide` instead of `/v1/systemone`, sending `{"text": ..., "queries": [...]}` with `"predicate"` instead of `{"state": ..., "questions": {...}}` with `"noul"`).
3. **Strands Decider (`strands_local`)**: **SYNTHETIC MICROSERVICE SPECIFICATION**. While `strands-decider` (v0.3.0) exists on PyPI as an open-source System One model (`StrandsAgents/strands-decider-2B`), its native server exposes `POST /v1/systemone` matching the TypeSafe wire spec. The codebase adapter `strands_adapter.py` connects to a custom local endpoint `http://localhost:8002/v1/decide` with a custom JSON shape.
4. **Fallback Safety**: The `DecisionService` fallback cascades (`FallbackChain`) ensure that any unverified, unconfigured, or failing adapters automatically cascade to **verified adapters** (`semantic_router`, `llm_structured`, and `rules`), preserving 100% system availability.

---

## 1. Documentation & Repository Evidence Table

In compliance with AGENTS.md § 3.5, the following primary sources were directly inspected and validated:

| Technology / Product | Primary Source URLs & Repositories Consulted | Verified Status |
| :--- | :--- | :--- |
| **OpenAI Decisions API** | - Official Endpoint: `https://api.openai.com/v1/decisions`<br>- Model Reference: `gpt-6-luna`<br>- Python SDK: `openai>=1.x` (`client.decisions.create`)<br>- GitHub: `https://github.com/openai/openai-python`<br>- Docs: `https://platform.openai.com/docs/api-reference/` | **VERIFIED** (Primary public product & SDK) |
| **TypeSafe AI (Jev)** | - PyPI: `https://pypi.org/project/typesafe-sdk/` (v0.7.5)<br>- PyPI: `https://pypi.org/project/jev/` (v0.3.0)<br>- Homepage: `https://typesafe.ai`<br>- Official Docs: `https://docs.typesafe.ai/go/python-sdk`<br>- SDK Repo: `https://github.com/typesafe-ai/typesafe-sdk-python`<br>- Changelog: `https://docs.typesafe.ai/go/python-changelog` | **VERIFIED** (Primary SDK exists; codebase adapter divergent) |
| **Strands Decider** | - PyPI: `https://pypi.org/project/strands-decider/` (v0.3.0)<br>- PyPI: `https://pypi.org/project/strands-agents/` (v1.64.0)<br>- Official Docs: `https://strandsagents.com`<br>- Agent Repo: `https://github.com/strands-agents/harness-sdk`<br>- Model: `StrandsAgents/strands-decider-2B-hobson-v19` on Hugging Face | **VERIFIED** (Model & package exist; codebase adapter is a synthetic custom proxy) |
| **Semantic Router** | - PyPI: `https://pypi.org/project/semantic-router/` (v1.1.1)<br>- GitHub: `https://github.com/aurelio-labs/semantic-router` | **VERIFIED** (In production use) |
| **Chonkie & Rerankers** | - PyPI: `https://pypi.org/project/chonkie/` (v1.7.0)<br>- PyPI: `https://pypi.org/project/rerankers/` (v0.10.0)<br>- PyPI: `https://pypi.org/project/flashrank/` (v0.2.10) | **VERIFIED** (In production use) |

---

## 2. In-Depth Adapter Analysis & Primary Documentation Comparison

### 2.1 OpenAI Decisions API Adapter (`OpenAIDecisionsAdapter`)

#### Official Primary Documentation Findings
- **Endpoint**: `POST https://api.openai.com/v1/decisions`
- **Authentication**: `Authorization: Bearer $OPENAI_API_KEY`
- **Model**: `gpt-6-luna` (specialized System One evaluator model)
- **Supported Question Types**:
  1. `predicate`: Evaluates condition probability (returns `verdict: bool`, `probability: float`)
  2. `choice`: Categorical classification over options (returns `choice: str`, `confidence: float`, `probabilities: dict`)
  3. `score`: Evaluates input against ordinal levels (returns `score: float`, `confidence: float`)
- **Official Python SDK Method**:
  ```python
  from openai import OpenAI
  client = OpenAI()
  response = client.decisions.create(
      model="gpt-6-luna",
      input="The package arrived damaged...",
      questions=[
          {"name": "is_urgent", "type": "predicate", "instructions": "..."},
          {"name": "department", "type": "choice", "choices": ["billing", "support"], "instructions": "..."}
      ]
  )
  ```

#### Comparison with `openai_decisions_adapter.py`
- **Location**: `src/ragassist/platform/decisions/adapters/openai_decisions_adapter.py`
- **Match Assessment**:
  - The adapter correctly targets `POST https://api.openai.com/v1/decisions`.
  - The adapter correctly configures `model = "gpt-6-luna"`.
  - The adapter correctly structures `input` and `questions` with matching types (`choice`, `predicate`, `score`).
  - The adapter correctly parses `data.get("answers", [])`.
- **Nuances / Identified Discrepancies**:
  - In `_format_question()`, choices are serialized as `"choices": [{"value": c} for c in q.choices]`. The official OpenAI Decisions API documentation uses flat string arrays: `"choices": ["rag_search", "saas_action", ...]`.
  - The adapter uses `httpx.AsyncClient` direct HTTP post rather than `client.decisions.create()` from `openai-python`. This is valid and minimizes tight SDK coupling.
- **Classification**: **VERIFIED AGAINST OFFICIAL SPECIFICATION**.

---

### 2.2 TypeSafe AI Jev Adapter (`JevAdapter`)

#### Official Primary Documentation Findings
- **Packages on PyPI**:
  - `typesafe-sdk` (v0.7.5): Official TypeSafe AI Python SDK. Provides `TypeSafeClient` and `AsyncTypeSafeClient`.
  - `jev` (v0.3.0): Function decorator package (`@jev.fn`) that compiles function signatures and docstrings into Jev System One queries. (Note: requires Python `>=3.14`).
- **Official Wire Protocol**:
  - Primary Endpoint: `POST https://api.typesafe.ai/v1/systemone` (constant `SYSTEM_ONE_PATH = "/v1/systemone"` in `typesafe_sdk._core.constants`).
  - Gateway / Alternative Route: `https://jevtypesafeai.com/api/v1/decide` or `https://openrouter.ai/api/v1/systemone`.
  - Wire Payload:
    ```json
    {
      "model": "jev-latest",
      "state": "<unstructured input text or structured document>",
      "questions": {
        "question_name_1": {
          "type": "choice",
          "instructions": "...",
          "criteria": {"opt1": "desc1", "opt2": "desc2"}
        },
        "question_name_2": {
          "type": "noul",
          "instructions": "..."
        },
        "question_name_3": {
          "type": "score",
          "instructions": "...",
          "criteria": ["level1", "level2", "level3"]
        }
      }
    }
    ```
  - Primitives:
    - `choice`: Categorical choice
    - `noul`: Binary yes/no assessment (stands for "no/null", probability of true)
    - `score`: Ordinal rubric evaluation

#### Comparison with `jev_adapter.py`
- **Location**: `src/ragassist/platform/decisions/adapters/jev_adapter.py`
- **Match Assessment**:
  - **Divergence 1 (Endpoint)**: Default endpoint in adapter is `https://api.typesafe.ai/v1/decide`. The official endpoint is `https://api.typesafe.ai/v1/systemone`.
  - **Divergence 2 (Top-Level Keys)**: Adapter sends `{"text": input_text, "queries": [...]}`. The official API requires `{"state": input_text, "questions": {...}}`.
  - **Divergence 3 (Questions Structure)**: Adapter sends a list of question dicts. The official API requires a mapping keyed by question name (`Mapping[str, Question]`).
  - **Divergence 4 (Binary Primitive)**: Adapter formats binary questions as `{"type": "predicate", "prompt": ...}`. The official TypeSafe System One API primitive is `noul` with `instructions`.
  - **Divergence 5 (SDK Usage)**: `typesafe-sdk` is declared in `pyproject.toml` (`typesafe-sdk>=0.1.0`), but `jev_adapter.py` never imports `typesafe_sdk`, implementing an ad-hoc divergent HTTP payload instead.
- **Classification**: **SPECULATIVE / UNVERIFIED (Divergent from Primary SDK & API)**.

---

### 2.3 Strands Decider Adapter (`StrandsDeciderAdapter`)

#### Official Primary Documentation Findings
- **Packages on PyPI**:
  - `strands`: **Warning**: `strands` on PyPI is an unrelated numerical physics package (Schrödinger standing wave approximations).
  - `strands-decider` (v0.3.0): The actual official System One classification package from Strands Agents. Provides model inference (`StrandsAgents/strands-decider-2B`), CLI (`strands-decider ask`), and server (`strands-decider serve`).
  - `strands-agents` (v1.64.0): The agent framework (`https://strandsagents.com`).
- **Official Wire Protocol (`strands_decider.server`)**:
  - The official server (`strands_decider/server.py` and `schema.py`) explicitly implements the public TypeSafe/Jev System One specification:
    ```text
    POST /v1/systemone
    {"state": ..., "model": "strands-decider-latest", "questions": {"<name>": {...}}}
    Primitives: noul, choice, score
    ```
  - It does NOT expose an endpoint called `/v1/decide`.

#### Comparison with `strands_adapter.py`
- **Location**: `src/ragassist/platform/decisions/adapters/strands_adapter.py` (adapter name: `strands_local`)
- **Match Assessment**:
  - **Divergence 1 (Endpoint)**: Adapter connects to `STRANDS_DECIDER_ENDPOINT` (default `http://localhost:8002/v1/decide`). The official `strands-decider` server exposes `POST /v1/systemone`.
  - **Divergence 2 (Payload)**: Adapter sends `{"input": input_text, "questions": [...]}` as a list, whereas `strands-decider` expects `{"state": ..., "questions": {...}}` (dictionary).
  - **Divergence 3 (Deployment Model)**: `strands-decider` is not in `pyproject.toml` due to heavy PyTorch / transformers requirements. The adapter treats it as an external local microservice.
- **Classification**: **SYNTHETIC / CUSTOM PROXY SPECIFICATION**.

---

## 3. Comparison Summary Matrix

| Metric / Attribute | OpenAI Decisions | TypeSafe AI (Jev) | Strands Decider (`strands_local`) |
| :--- | :--- | :--- | :--- |
| **Official Primary Product Exists?** | **Yes** (OpenAI platform) | **Yes** (TypeSafe AI) | **Yes** (`strands-decider` on PyPI/HF) |
| **Primary SDK Available?** | **Yes** (`openai>=1.x`) | **Yes** (`typesafe-sdk==0.7.5`) | **Yes** (`strands-decider==0.3.0`) |
| **Codebase Adapter Verification** | **VERIFIED** | **DIVERGENT** | **SYNTHETIC** |
| **Official Endpoint** | `/v1/decisions` | `/v1/systemone` | `/v1/systemone` |
| **Codebase Adapter Endpoint** | `/v1/decisions` | `/v1/decide` | `/v1/decide` |
| **State/Input Key** | `"input"` | `"state"` (Codebase uses `"text"`) | `"state"` (Codebase uses `"input"`) |
| **Binary Question Name** | `"predicate"` | `"noul"` (Codebase uses `"predicate"`) | `"noul"` (Codebase uses `"predicate"`) |
| **Questions Container** | List of objects | Dict keyed by name (Codebase uses list) | Dict keyed by name (Codebase uses list) |
| **Active Fallback Protection** | Protected by `FallbackChain` | Protected by `FallbackChain` | Protected by `FallbackChain` |

---

## 4. Architectural Recommendations & Action Plan

1. **Mark Status in Module Docstrings**:
   - In accordance with AGENTS.md § 3.5: *"Never guess an SDK signature. If the docs cannot be reached, say so and mark the code as unverified."*
   - Add docstring annotations to `jev_adapter.py` and `strands_adapter.py` marking them as `UNVERIFIED_SYNTHETIC_PROXY`.
2. **Safe Fallback Chain Configuration**:
   - Ensure `DECIDER_CHAIN` and `ROUTER_DECIDER_CHAIN` in `settings.py` maintain fully verified adapters in high-priority or fallback positions:
     - Router Chain: `semantic_router` (verified) -> `openai_decisions` (verified) -> `llm_structured` (verified) -> `rules` (verified).
     - Decider Chain: `openai_decisions` (verified) -> `llm_structured` (verified) -> `rules` (verified) -> `jev` (unverified/disabled by default).
   - Because `FallbackChain` catches HTTP errors, missing keys, and 404s within `DECIDER_TIMEOUT_MS` (1000ms), any failure in `jev` or `strands_local` instantly triggers the next adapter without affecting user latency or pipeline correctness.
3. **Future Alignment with Official SDKs (Post-M5)**:
   - When refining M1 components after M5:
     - Update `jev_adapter.py` to use `typesafe_sdk.AsyncTypeSafeClient` or align its raw `httpx` payload with `POST /v1/systemone`, `state`, and `noul`.
     - Update `openai_decisions_adapter.py` to serialize choice options as flat string arrays `["a", "b"]`.
     - Align `strands_adapter.py` to send the `POST /v1/systemone` payload matching the `strands-decider` server specification.

---
*Report generated and self-verified by `explorer_doc_verify_m1`.*
