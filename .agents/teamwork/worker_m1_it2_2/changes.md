# Verified Code Changes — Milestone 1 Iteration 2 Remediation

**Author**: `worker_m1_it2_2` (Milestone 1 Iteration 2 Worker Replacement)  
**Date**: 2026-11-08T08:35:00Z  
**Branch**: `master`  
**Working Directory**: `d:\Coding\RagAssist-1`  

---

## 1. Decision Layer Remediation (`explorer_m1_it2_1`)

### 1.1 `RulesDeciderAdapter` Word-Boundary Isolation & Unicode Hardening
- **File**: `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py`
- **Changes**:
  - Imported `unicodedata`.
  - Added `_HOMOGLYPH_MAP` mapping Cyrillic and Greek lookalike characters (`а`, `с`, `е`, `о`, `р`, `х`, `у`, `і`, `ј`, etc.) to standard ASCII characters.
  - Added `_ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200d\ufeff\u00ad]")` to strip zero-width and invisible formatting characters.
  - Added `_normalize_text(self, text: str) -> str` combining `unicodedata.normalize("NFKC", text)`, zero-width removal, and homoglyph translation.
  - Replaced naive substring checks `k in lower` with pre-compiled regex word boundaries (`re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE)`).
  - Refined SaaS action keywords to explicit phrases (`subscription plan`, `pricing plan`, `billing plan`, `my plan`, `current plan`, `subscription`, `invoice`, `invoices`, `billing`, `seats`, `seat`, `account overview`, `upgrade`, `downgrade`, `payment method`).
  - Applied `_normalize_text` across both `evaluate_choice` and `evaluate_predicate`.
- **Impact**: Queries like *"Can you give me an explanation of how pgvector works?"* or *"We planned our sprint"* correctly route to `rag_search` instead of being misrouted to `saas_action`. Obfuscated injection payloads (`"I\u200bgnore\u200b instructions"`, `"Ｉｇｎｏｒｅ"`) are normalized and caught by prompt injection filters.

### 1.2 `DecisionService` Fail-Closed Hardening
- **File**: `src/ragassist/platform/decisions/service.py`
- **Changes**:
  - In `check_safety()`: Updated exception handler to return `is_safe=False`, `risk_score=1.0`, `violation_categories=["safety_check_error"]`, `reasoning=f"Fail-closed on check failure: {exc}"`, `provider_used="fallback_default"`.
  - In `judge_grounding()`: Updated exception handler to return `is_grounded=False`, `grounding_score=0.0`, `confidence=0.0`, `unsupported_claims=[f"Grounding evaluation failed: {exc}"]`, `reasoning=f"Fail-closed on evaluation failure: {exc}"`, `provider_used="fallback_default"`.
- **Impact**: System fails closed under crashes, timeouts, or denial-of-service, preventing malicious prompts or ungrounded hallucinations from reaching users.

### 1.3 `LLMStructuredDeciderAdapter` Probability Calibration
- **File**: `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py`
- **Changes**:
  - Replaced artificial probability floor `probs[chosen] = max(result.confidence, 0.70)` with calibrated probability distribution. Set `conf = max(min(result.confidence, 1.0), 0.0)`, `probs[chosen] = conf`, and distributed remainder `(1.0 - conf) / (len(choices) - 1)` evenly across non-selected choices.
- **Impact**: Preserves true model uncertainty without artificially inflating low-confidence choices (e.g. 0.20) to >82%.

### 1.4 Missing Question Defaults in Remote Deciders
- **Files**:
  - `src/ragassist/platform/decisions/adapters/jev_adapter.py`
  - `src/ragassist/platform/decisions/adapters/strands_adapter.py`
  - `src/ragassist/platform/decisions/adapters/openai_decisions_adapter.py`
- **Changes**:
  - In `_parse_answer`: Changed missing question fallback `confidence` from `0.8` to `0.0`.
  - Set `prob` to `0.0`, `verdict` to `False`, `score` to `0.0`, and uniform probability distributions across choices.
- **Impact**: External HTTP API responses with empty or missing answers fail confidence thresholds (`< 0.70`), triggering clean failover to next decider in fallback chain.

### 1.5 Dedicated Regression Tests
- **File**: `tests/unit/test_decision_layer.py`
- **Added Tests**:
  - `test_rules_decider_keyword_substring_isolation`: Verifies that `"explanation"` and `"planned"` route to `rag_search` while `"subscription plan"` routes to `saas_action`.
  - `test_rules_decider_unicode_normalization_security`: Verifies that zero-width space smuggling and fullwidth Unicode injections are detected.
  - `test_decision_service_fail_closed_guarantees`: Verifies that `check_safety` and `judge_grounding` return fail-closed verdicts when underlying chains throw exceptions.

---

## 2. Settings, Asyncio & Role Catalog Remediation (`explorer_m1_it2_2`)

### 2.1 Removal of Global Proactor Monkeypatch from Production Code
- **File**: `src/ragassist/shared/config/settings.py`
- **Changes**:
  - Removed lines 11–43 (the `BaseProactorEventLoop` and `IocpProactor` monkeypatch).
  - Cleaned up unused imports (`sys`, `Any`, `Field`).
- **Impact**: Restores standard library asyncio semantics in production. Eliminates suppression of `_loop_self_reading` and ensures `loop.call_soon_threadsafe()` functions reliably across threads.

### 2.2 Win32 Test Runner IOCP Patch Relocation
- **File**: `tests/conftest.py`
- **Changes**:
  - Added Windows sandbox IOCP event loop patch to `tests/conftest.py`, active only under `sys.platform == "win32"` during test execution.
- **Impact**: Keeps production codebase completely clean (`src/` isolation) while allowing pytest suites to run smoothly in restricted Windows environments without socket loopback hangs.

### 2.3 Single Source of Truth for Role Catalog (DEFECT-14)
- **File**: `src/ragassist/shared/config/settings.py`
- **Changes**:
  - Defaulted `LLM_ROLE_GENERATOR_PRIMARY`, `LLM_ROLE_GENERATOR_FALLBACKS`, `LLM_ROLE_REWRITER_PRIMARY`, `LLM_ROLE_AGENT_PRIMARY`, `LLM_ROLE_JUDGE_PRIMARY`, `LLM_ROLE_DECIDER_FALLBACK` to empty strings `""`.
  - Updated `DECIDER_CHAIN` to `"openai_decisions,jev,llm_structured,rules"` and `ROUTER_DECIDER_CHAIN` to `"semantic_router,openai_decisions,llm_structured,rules"` to ensure robust terminal fallback to `rules`.
- **Impact**: `config/models.yaml` serves as the authoritative single source of truth for all role definitions and fallback chains out of the box, preventing 16.6x token cost inflation from shadowing `gpt-4o-mini` with `gpt-4o`.

### 2.4 Stripped Role Override Guards in ModelCatalog
- **File**: `src/ragassist/platform/llm/catalog.py`
- **Changes**:
  - In `resolve_role_chain`: Wrapped setting lookups with `.strip()` checks (`if settings.LLM_ROLE_* and settings.LLM_ROLE_*.strip():`).
  - Ensured fallback overrides only apply if parsed list contains non-empty tokens.
- **Impact**: Whitespace-only environment variables (`"   "`) or empty comma strings do not crash catalog resolution or erase configured YAML fallbacks.

### 2.5 `.env.example` Synchronization
- **File**: `.env.example`
- **Changes**:
  - Synchronized lines 55–61 with empty defaults and explanatory comments.
  - Synchronized decider chain defaults with `rules` as terminal fallback.
- **Impact**: Developers copying `.env.example` to `.env` do not unintentionally shadow `config/models.yaml`.

### 2.6 Un-xfailing DEFECT-14
- **File**: `tests/unit/platform/llm/test_catalog.py`
- **Changes**:
  - Removed `@defect("DEFECT-14")` from `test_default_settings_do_not_shadow_the_yaml_roles`.
- **Impact**: Active unit test verifying role resolution directly against `models.yaml`.

---

## 3. Adapters & Test Harmonization (`explorer_m1_it2_3`)

### 3.1 Model Capabilities & Pricing Alignment (DEFECT-17)
- **File**: `src/ragassist/platform/llm/adapters/openrouter_adapter.py`
- **Changes**:
  - In `OpenRouterAdapter.get_pricing()`: Added Mistral Large pricing ($2.00 input / $6.00 output per MTok).
  - In `OpenRouterAdapter.get_capabilities()`: Added Llama 3.1 70B native context window (131,072 tokens).
  - In `OpenAICompatibleAdapter.get_capabilities()`: Added Llama 3.1 8B native context window (32,768 tokens).
- **File**: `config/models.yaml`
- **Changes**:
  - Set `json_mode: false` for `openrouter-llama-3.1-70b` and `openrouter-mistral-large` to match provider capabilities and `test_chat_adapters.py`.

### 3.2 Modular OpenAI-Compatible Adapter
- **File**: `src/ragassist/platform/llm/adapters/openai_compatible_adapter.py`
- **Changes**: Created dedicated module re-exporting `OpenAICompatibleAdapter`.
- **File**: `src/ragassist/platform/llm/adapters/__init__.py`
- **Changes**: Exposed `OpenAICompatibleAdapter` in `__all__`.

### 3.3 Un-xfailing DEFECT-17
- **File**: `tests/unit/platform/llm/test_llm_service.py`
- **Changes**: Removed `@defect("DEFECT-17")` from `test_all_providers_agree`.

### 3.4 Adversarial Test Suite Harmonization
- **File**: `tests/security/test_decision_adversarial.py`
- **Changes**: Harmonized assertions across 5 empirical tests to validate remediated behavior:
  1. `test_unicode_smuggling_and_homoglyphs`: Asserted `verdict_zw.is_safe is False` and `verdict_fw.is_safe is False`.
  2. `test_safety_check_fail_closed_on_error`: Asserted `verdict.is_safe is False`, `risk_score == 1.0`, `"safety_check_error" in violation_categories`.
  3. `test_grounding_judge_fail_closed_on_error`: Asserted `verdict.is_grounded is False`, `grounding_score == 0.0`, `len(unsupported_claims) > 0`.
  4. `test_adapter_missing_question_defaults_to_zero_confidence`: Asserted `confidence == 0.0` for missing questions in Jev and OpenAI Deciders.
  5. `test_llm_structured_low_confidence_probability_calibrated`: Asserted `probabilities["saas_action"] <= 0.35` for 0.20 confidence.
