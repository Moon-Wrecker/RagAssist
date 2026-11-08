# Handoff Report — Milestone 1 Iteration 2 Explorer 1 (Decision Layer Remediation Specialist)

**Agent**: Explorer 1 (`explorer_m1_it2_1`)  
**Roles**: Decision Layer Remediation Specialist, Investigator, Synthesizer  
**Working Directory**: `d:\Coding\RagAssist-1`  
**State Folder**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_it2_1`  
**Parent Agent**: `be9621e6-d3bc-446a-abb9-2d0c46239ab1`  
**Date**: 2026-11-07T21:37:00Z  

---

## 1. Observation

### 1.1 Direct Source Code Observations

#### A. Finding 1: Naive Substring Matching and Missing Unicode Normalization in `RulesDeciderAdapter`
- **File**: `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py:86-88`
  ```python
  86:             if any(k in lower for k in self._saas_action_keywords):
  87:                 probs = {"saas_action": 0.92, "rag_search": 0.05, "general_chat": 0.02, "human_escalation": 0.01}
  88:                 return ChoiceAnswer(name=question.name, choice="saas_action", confidence=0.92, probabilities=probs)
  ```
  - `_saas_action_keywords` contains `"plan"`.
  - In Python: `"plan" in "Can you give me an explanation of how pgvector works?".lower()` evaluates to `True`.
  - Non-action words like `"explanation"`, `"planned"`, and `"planner"` are routed to `saas_action` with 0.92 confidence instead of `rag_search`.
- **File**: `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py:116`
  ```python
  116:             is_injected = any(pattern.search(input_text) for pattern in self._injection_patterns)
  ```
  - Direct regex search over raw `input_text` without Unicode normalization (`unicodedata.normalize("NFKC", ...)`) or zero-width space filtering permits evasion via fullwidth characters (`Ｉｇｎｏｒｅ`), zero-width spaces (`I\u200bgnore`), and Cyrillic homoglyphs (`Ign\u043ere`).

#### B. Finding 2: Fail-Open Vulnerabilities in `DecisionService`
- **File**: `src/ragassist/platform/decisions/service.py:136-144` (`check_safety`)
  ```python
  136:         except Exception as exc:
  137:             logger.warning("decision_service.check_safety_failed", error=str(exc))
  138:             # Fail closed or safe default
  139:             return SafetyVerdict(
  140:                 is_safe=True,
  141:                 risk_score=0.0,
  142:                 reasoning=f"Safe default on check failure: {exc}",
  143:                 provider_used="fallback_default",
  144:             )
  ```
  - Caught exception defaults to `is_safe=True` and `risk_score=0.0`, failing open on safety evaluation errors or provider timeouts.
- **File**: `src/ragassist/platform/decisions/service.py:221-230` (`judge_grounding`)
  ```python
  221:         except Exception as exc:
  222:             logger.warning("decision_service.judge_grounding_failed", error=str(exc))
  223:             return GroundingVerdict(
  224:                 grounding_score=0.70,
  225:                 is_grounded=True,
  226:                 unsupported_claims=[],
  227:                 confidence=0.50,
  228:                 reasoning=f"Default grounded on evaluation failure: {exc}",
  229:                 provider_used="fallback_default",
  230:             )
  ```
  - Caught exception defaults to `is_grounded=True` with `grounding_score=0.70`, delivering unverified hallucinations directly to users during evaluation errors.

#### C. Finding 3: Probability Inflation in `LLMStructuredDeciderAdapter`
- **File**: `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py:82-87`
  ```python
  82:             probs = {c: 0.05 for c in question.choices}
  83:             probs[chosen] = max(result.confidence, 0.70)
  84:             # Re-normalize
  85:             total = sum(probs.values())
  86:             probs = {c: p / total for c, p in probs.items()}
  ```
  - Forcing `probs[chosen] = max(result.confidence, 0.70)` inflates low-confidence outputs (e.g., `confidence=0.20`) to $>82\%$ probability after re-normalization.

#### D. Finding 4: Default Confidence 0.8 for Missing Questions in Remote Adapters
- **Files**:
  - `src/ragassist/platform/decisions/adapters/jev_adapter.py:68, 79`
  - `src/ragassist/platform/decisions/adapters/strands_adapter.py:66, 77`
  - `src/ragassist/platform/decisions/adapters/openai_decisions_adapter.py:74, 85`
  ```python
  confidence = float(raw.get("confidence", 0.8))
  ```
  - When the remote API response omits a question or returns `{"answers": []}`, `raw` is `{}` and `confidence` defaults to `0.8`. Because `0.8 >= 0.70` (`DECIDER_MIN_CONFIDENCE`), an un-evaluated answer is accepted as authoritative and does not trigger fallback cascades.

#### E. Test Suite Status
- Ran: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_decision_layer.py -v` -> 9 passed in 12.91s.
- Ran: `.\.venv\Scripts\python.exe -m pytest tests/security/test_decision_adversarial.py -v` -> 25 passed in 15.25s.
- Observed that 5 tests in `test_decision_adversarial.py` currently assert the *presence* of these defects as empirical evidence for Iteration 1 rejection (`test_safety_check_fail_open_observation`, `test_grounding_judge_fail_open_on_error_observation`, `test_adapter_missing_question_defaults_to_high_confidence`, `test_llm_structured_low_confidence_probability_inflation`, and `test_unicode_smuggling_and_homoglyphs`).

---

## 2. Logic Chain

1. **Premise 1 (Routing Precision)**: An intent router must not trigger high-confidence action routing on informational requests.
2. **Observation 1.1.A**: Substring check `k in lower` for `"plan"` triggers on `"explanation"`.
3. **Inference 1**: Replacing substring containment with pre-compiled regex word boundaries (`rf"\b{re.escape(k)}\b"`) strictly restricts matching to the standalone word `"plan"`, isolating words like `"explanation"` and `"planned"`.
4. **Premise 2 (Zero-Trust Security)**: Security guardrails and grounding judges must fail closed. Under network failure, rate limiting, or malformed input, unverified queries or hallucinated content must not bypass security barriers.
5. **Observation 1.1.B**: Both `check_safety` and `judge_grounding` return permissive defaults (`is_safe=True`, `is_grounded=True`) on exceptions.
6. **Inference 2**: Hardening the exception handlers to return `is_safe=False`, `risk_score=1.0`, `violation_categories=["safety_check_error"]` and `is_grounded=False`, `grounding_score=0.0`, `confidence=0.0` ensures strict fail-closed security.
7. **Premise 3 (Calibration Fidelity)**: System One decision probabilities must accurately reflect the model's confidence distribution.
8. **Observation 1.1.C & 1.1.D**: Artificial clamping to 0.70 in `llm_structured_adapter` and defaulting missing questions to 0.8 in remote adapters distort confidence ratings and disable the resilience fallback chain.
9. **Inference 3**: Changing the floor to `max(result.confidence, 0.05)` and missing question defaults to `0.0` restores calibrated probability distributions and activates automatic fallback cascades when confidence $< 0.70$.
10. **Conclusion**: Applying these targeted technical fixes completely resolves the four defects without architectural breakage, providing a clean path to Milestone 1 sign-off.

---

## 3. Caveats

- **Scope Boundary**: As Explorer 1, in strict accordance with the read-only constraint, no production files or tests were modified during this investigation. All remediation specifications are fully documented in `analysis_decision_remediation.md` for immediate application by the implementation worker.
- **Adversarial Test Synchronization**: The worker must update the assertions in `tests/security/test_decision_adversarial.py` (specifically tests documenting the defect observations) in tandem with applying the source fixes, otherwise the adversarial suite will fail because it originally asserted the presence of the defect.

---

## 4. Conclusion

The Decision Layer defects from Iteration 1 Gate have been fully investigated and resolved at the design level. An exhaustive specification containing before/after code blocks, regex patterns, Unicode normalization logic, and test migration details has been authored and saved to:
`d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_it2_1\analysis_decision_remediation.md`

### Summary of Actionable Specifications Delivered:
1. `RulesDeciderAdapter`:
   - Import `unicodedata`.
   - Add `_normalize_text(text: str)` performing NFKC normalization, zero-width space removal (`[\u200b-\u200d\ufeff\u00ad]`), and Cyrillic homoglyph translation.
   - Pre-compile word-boundary regexes `\b{k}\b` for `_saas_action_keywords` and `_escalation_keywords`.
   - Apply normalization across `evaluate_choice` and `evaluate_predicate`.
2. `DecisionService`:
   - `check_safety`: Fail-closed (`is_safe=False`, `risk_score=1.0`, `violation_categories=["safety_check_error"]`).
   - `judge_grounding`: Fail-closed (`is_grounded=False`, `grounding_score=0.0`, `confidence=0.0`).
3. `LLMStructuredDeciderAdapter`:
   - Line 83: Replace `max(result.confidence, 0.70)` with `max(result.confidence, 0.05)`.
4. Decider Adapters (`jev_adapter.py`, `strands_adapter.py`, `openai_decisions_adapter.py`):
   - Replace default confidence `0.8` with `0.0` for missing question parsing.
5. Test Plan:
   - Synchronize 5 adversarial test assertions in `tests/security/test_decision_adversarial.py`.
   - Add 3 regression-prevention unit test functions in `tests/unit/test_decision_layer.py`.

---

## 5. Verification Method

To independently verify the proposed remediation after implementation:
1. Run decision layer unit tests:
   ```powershell
   & .\.venv\Scripts\python.exe -m pytest tests/unit/test_decision_layer.py -v
   ```
2. Run adversarial security suite:
   ```powershell
   & .\.venv\Scripts\python.exe -m pytest tests/security/test_decision_adversarial.py -v
   ```
3. Run full test suite:
   ```powershell
   & .\.venv\Scripts\python.exe -m pytest -v
   ```
4. Verify keyword isolation in Python:
   ```python
   from ragassist.platform.decisions.adapters.rules_decider_adapter import RulesDeciderAdapter
   from ragassist.platform.decisions.ports import ChoiceQuestion
   import asyncio

   rules = RulesDeciderAdapter()
   q = ChoiceQuestion(name="route", instructions="route", choices=["rag_search", "saas_action", "general_chat", "human_escalation"])
   ans = asyncio.run(rules.evaluate_choice("Can you give me an explanation of the RAG architecture?", q))
   assert ans.choice == "rag_search", f"Expected rag_search, got {ans.choice}"
   ```
