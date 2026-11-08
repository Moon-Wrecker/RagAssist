# Handoff Report — Milestone 1 Challenger 2 (Adversarial Verification of Decision Layer & Guardrails)

## Verdict: REQUEST_CHANGES

---

## 1. Observation

### Empirical Test Execution

Adversarial stress suite was written to `tests/security/test_decision_adversarial.py` and executed via `run_command` with `BypassSandbox=True`:
```powershell
& .\.venv\Scripts\python.exe -m pytest tests/security/test_decision_adversarial.py -v
```

Verbatim execution log:
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0
Using --randomly-seed=3337255425
rootdir: D:\Coding\RagAssist-1
configfile: pyproject.toml
plugins: anyio-4.16.0, Faker-40.44.0, hypothesis-6.170.15, langsmith-0.14.17, asyncio-1.4.1.post1, cov-7.1.0, randomly-5.0.0, timeout-2.4.0, respx-0.23.1, time-machine-3.6.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
timeout: 30.0s
timeout method: thread
timeout func_only: False
collected 25 items

tests\security\test_decision_adversarial.py .........................    [100%]

============================= 25 passed in 11.60s =============================
```

Existing unit tests under `tests/unit/test_decision_layer.py`:
```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/test_decision_layer.py -v
```
Output:
```
tests\unit\test_decision_layer.py .........                              [100%]
============================= 9 passed in 10.88s ==============================
```

---

### Directly Observed Code Defects & Vulnerabilities

#### Defect 1: Critical Security — Fail-Open on Safety Check Failure
**File**: `src/ragassist/platform/decisions/service.py:136-144`
```python
        except Exception as exc:
            logger.warning("decision_service.check_safety_failed", error=str(exc))
            # Fail closed or safe default
            return SafetyVerdict(
                is_safe=True,
                risk_score=0.0,
                reasoning=f"Safe default on check failure: {exc}",
                provider_used="fallback_default",
            )
```
- **Observed Behavior**: Despite the code comment stating `# Fail closed or safe default`, the exception handler returns `is_safe=True` with `risk_score=0.0`.
- **Empirical Proof**: Verified by `test_safety_check_fail_open_observation`. When all safety deciders fail, timeout, or crash (e.g. DoS payload, external provider 5xx/429, or unhandled token length), adversarial prompt injection attacks pass completely undetected.

#### Defect 2: High Integrity — Fail-Open on Grounding Judge Failure
**File**: `src/ragassist/platform/decisions/service.py:222-230`
```python
        except Exception as exc:
            logger.warning("decision_service.judge_grounding_failed", error=str(exc))
            return GroundingVerdict(
                grounding_score=0.70,
                is_grounded=True,
                unsupported_claims=[],
                confidence=0.50,
                reasoning=f"Default grounded on evaluation failure: {exc}",
                provider_used="fallback_default",
            )
```
- **Observed Behavior**: When grounding verification fails or times out, the service returns `is_grounded=True` with a manufactured `grounding_score=0.70`.
- **Empirical Proof**: Verified by `test_grounding_judge_fail_open_on_error_observation`. Wild hallucinations and fabricated claims bypass post-generation grounding and are delivered directly to users upon provider failure.

#### Defect 3: Calibration Distortion in `LLMStructuredDeciderAdapter`
**File**: `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py:83`
```python
            probs = {c: 0.05 for c in question.choices}
            probs[chosen] = max(result.confidence, 0.70)
            # Re-normalize
            total = sum(probs.values())
            probs = {c: p / total for c, p in probs.items()}
```
- **Observed Behavior**: The chosen option probability is clamped to `max(result.confidence, 0.70)`.
- **Empirical Proof**: Verified by `test_llm_structured_low_confidence_probability_inflation`. When the LLM explicitly reports very low confidence (e.g., `confidence=0.20`), the returned probability distribution calculates `probabilities[chosen] = 0.70 / (0.70 + 3 * 0.05) = 0.8235` (>82%), directly contradicting the `confidence` score (0.20).

#### Defect 4: Missing Question in Decider Response Defaults to High Confidence (0.8)
**Files**:
- `src/ragassist/platform/decisions/adapters/jev_adapter.py:68`
- `src/ragassist/platform/decisions/adapters/strands_adapter.py:66`
- `src/ragassist/platform/decisions/adapters/openai_decisions_adapter.py:74`
```python
        if isinstance(q, ChoiceQuestion):
            choice = raw.get("choice", q.choices[0] if q.choices else "")
            confidence = float(raw.get("confidence", 0.8))
            probs = raw.get("probabilities", {c: 0.1 for c in q.choices})
            return ChoiceAnswer(name=q.name, choice=choice, confidence=confidence, probabilities=probs)
```
- **Observed Behavior**: If the remote decider API returns an empty `answers` list or omits the question, `raw` is `{}` and `confidence` defaults to `0.8`.
- **Empirical Proof**: Verified by `test_adapter_missing_question_defaults_to_high_confidence`. Because `0.8 >= 0.70` (`DECIDER_MIN_CONFIDENCE`), an un-evaluated query is mistakenly accepted as a high-confidence decision.

#### Defect 5: Unicode Evasion and Semantic Paraphrases in `RulesDeciderAdapter`
**File**: `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py:23-30`
```python
        self._injection_patterns = [
            re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
            re.compile(r"dump\s+(?:the\s+)?system\s+prompt", re.IGNORECASE),
            re.compile(r"you\s+are\s+now\s+in\s+dan\s+mode", re.IGNORECASE),
            re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
            re.compile(r"reveal\s+(?:your\s+)?(?:system\s+)?instructions", re.IGNORECASE),
            re.compile(r"jailbreak", re.IGNORECASE),
        ]
```
- **Observed Behavior**: Missing Unicode NFKC normalization and reliance on static regexes allows zero-width space smuggling (`I\u200bgnore previous instructions`), Cyrillic homoglyphs (`Ign\u043ere`), fullwidth characters (`Ｉｇｎｏｒｅ`), and basic paraphrases ("Disregard preceding instructions", "Forget all prior context") to bypass the rules filter.
- **Empirical Proof**: Verified by `test_unicode_smuggling_and_homoglyphs` and `test_subtle_and_paraphrased_injection_gaps_in_rules`.

---

### Robustness & Compliant Behaviors Verified

1. **Confidence Fallback Cascade Boundary**:
   - `test_exact_boundary_above_threshold_0_7001`: Confirmed `confidence=0.7001` is accepted by primary decider; secondary decider is NOT called.
   - `test_exact_boundary_exact_threshold_0_7000`: Confirmed `confidence=0.7000` is accepted; secondary decider is NOT called.
   - `test_exact_boundary_below_threshold_0_6999_cascades`: Confirmed `confidence=0.6999` is rejected; secondary decider is invoked.
   - `test_all_deciders_below_confidence_fallback_default`: Confirmed graceful fallback to `rag_search` default with `confidence=0.50` when all deciders fail confidence check.
2. **Timeout Cascade**:
   - `test_decider_timeout_cascade`: Confirmed that when a decider hangs beyond `DECIDER_TIMEOUT_MS` (50ms in test), `asyncio.wait_for` raises `TimeoutError` and cascades immediately to the next provider.
3. **Intent Router Input Stress**:
   - Empty/whitespace queries (`""`, `"   "`, `"\t\n"`): Successfully handled without crashing (`test_empty_and_whitespace_only_queries`).
   - Huge inputs (>20,000 characters): Evaluated in < 0.25s without ReDoS or event loop blocking (`test_huge_input_dos_resilience`).
   - Illegal route strings: Normalized safely to `"rag_search"` (`test_malformed_route_normalization`).
   - Multi-intent queries: Priorities respected (`human_escalation` > `saas_action` > `general_chat` > `rag_search`).

---

## 2. Logic Chain

1. **Safety Premise**: An input guardrail must protect downstream LLM synthesis from prompt injections. Under adverse conditions (timeout, external API outage, network drop, or malformed input), failing open (`is_safe=True`, `risk_score=0.0`) renders the guardrail ineffective against Denial-of-Service or flood-based bypasses.
2. **Grounding Premise**: Hallucination detection verifies that generated responses do not present unverified factual claims. Returning `is_grounded=True` with fabricated `grounding_score=0.70` when the grounding decider crashes enables unverified hallucinations to reach users undetected.
3. **Calibration Premise**: The decision layer's architectural contract requires calibrated confidence ratings for System One routing and grading. Forcing `probs[chosen] = max(result.confidence, 0.70)` in `LLMStructuredDeciderAdapter` distorts low-confidence outputs, and defaulting missing questions to `confidence=0.8` in `JevAdapter`, `StrandsDeciderAdapter`, and `OpenAIDecisionsAdapter` bypasses the 0.70 minimum confidence filter.
4. **Conclusion**: While the core routing, timeout cascades, and boundary comparison logic function correctly, the presence of two fail-open safety/grounding fallbacks and two probability distortion bugs compromises system security and integrity.

---

## 3. Caveats

- Tests involving external APIs (`JevAdapter`, `OpenAIDecisionsAdapter`) were executed with mocked HTTP endpoints (`respx`) to isolate protocol parsing from external network availability.
- No source files under `src/` were modified by Challenger 2, adhering strictly to the review-only constraint.
- The failure in `tests/unit/test_adversarial_m1.py` belongs to Challenger 1's domain (`ModelCatalog` alias resolution) and is noted for situational awareness.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

The following concrete fixes must be applied by the worker:

1. **Fix `check_safety` Fallback (Fail-Closed)**:
   In `src/ragassist/platform/decisions/service.py:136-144`, change fallback to fail-closed or flag for review:
   ```python
   except Exception as exc:
       logger.warning("decision_service.check_safety_failed", error=str(exc))
       return SafetyVerdict(
           is_safe=False,
           violation_categories=["safety_check_error"],
           risk_score=1.0,
           reasoning=f"Fail-closed on check failure: {exc}",
           provider_used="fallback_default",
       )
   ```
2. **Fix `judge_grounding` Fallback (Fail-Closed / Escalation)**:
   In `src/ragassist/platform/decisions/service.py:222-230`, change fallback to ungrounded or trigger escalation:
   ```python
   except Exception as exc:
       logger.warning("decision_service.judge_grounding_failed", error=str(exc))
       return GroundingVerdict(
           grounding_score=0.0,
           is_grounded=False,
           unsupported_claims=[f"Grounding evaluation failed: {exc}"],
           confidence=0.0,
           reasoning=f"Fail-closed on evaluation failure: {exc}",
           provider_used="fallback_default",
       )
   ```
3. **Fix Probability Distortion in `LLMStructuredDeciderAdapter`**:
   In `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py:83`, replace `max(result.confidence, 0.70)` with the true calibrated `result.confidence`:
   ```python
   probs = {c: 0.05 for c in question.choices}
   probs[chosen] = max(result.confidence, 0.05)
   ```
4. **Fix Missing Field Default in Decider Adapters**:
   In `jev_adapter.py:68`, `strands_adapter.py:66`, and `openai_decisions_adapter.py:74`, change `raw.get("confidence", 0.8)` to `raw.get("confidence", 0.0)` or raise a descriptive parsing error when the question is not present in `data["answers"]`.
5. **Add Unicode NFKC Normalization**:
   In `RulesDeciderAdapter`, normalize input text using `unicodedata.normalize("NFKC", input_text)` prior to regex evaluation.

---

## 5. Verification Method

Run the newly created adversarial suite:
```powershell
& .\.venv\Scripts\python.exe -m pytest tests/security/test_decision_adversarial.py -v
```
Expected result: `25 passed in ~11-12s`.

Run the full decision layer unit suite:
```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/test_decision_layer.py -v
```
Expected result: `9 passed in ~10s`.

Inspect files:
- `tests/security/test_decision_adversarial.py`
- `src/ragassist/platform/decisions/service.py`
- `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py`
- `src/ragassist/platform/decisions/adapters/jev_adapter.py`
- `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py`
