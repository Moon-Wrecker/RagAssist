# Adversarial Verification Report: Decision Layer & Guardrails

**Challenger**: `challenger_m1_it2_2` (Milestone 1 Iteration 2 Challenger 2)  
**Date**: 2026-11-08T08:59:00Z  
**Verdict**: **APPROVE**  

---

## 1. Observation

Direct empirical evidence collected via executing the security, unit, and adversarial challenger stress test suites:

### 1.1 Test Suite Executions

1. **Adversarial Security Test Suite (`tests/security/test_decision_adversarial.py`)**:
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/security/test_decision_adversarial.py -v`
   - Output:
     ```text
     collected 25 items
     tests\security\test_decision_adversarial.py .........................    [100%]
     ============================= 25 passed in 9.34s ==============================
     ```

2. **Decision Layer Unit Test Suite (`tests/unit/test_decision_layer.py`)**:
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_decision_layer.py -v`
   - Output:
     ```text
     collected 12 items
     tests\unit\test_decision_layer.py ............                           [100%]
     ============================= 12 passed in 8.20s ==============================
     ```

3. **Challenger Adversarial Stress Harness (`tests/security/test_empirical_challenger_stress.py`)**:
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/security/test_empirical_challenger_stress.py -v`
   - Output:
     ```text
     collected 16 items
     tests\security\test_empirical_challenger_stress.py ................      [100%]
     ============================= 16 passed in 13.21s =============================
     ```

Total verified passed: **53 tests (100% pass rate)**.

### 1.2 Specific Code Invariants Observed

1. **NFKC Normalization, Homoglyph Mapping & Zero-Width Stripping**:
   - In `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py:20-27`:
     ```python
     _HOMOGLYPH_MAP = str.maketrans({
         "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y",
         "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
         "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "І": "I", "Ј": "J",
         "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X",
     })
     _ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200d\ufeff\u00ad]")
     ```
   - In `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py:93-97`:
     ```python
     def _normalize_text(self, text: str) -> str:
         """Normalize Unicode, strip zero-width characters, and map homoglyphs."""
         norm = unicodedata.normalize("NFKC", text)
         cleaned = _ZERO_WIDTH_PATTERN.sub("", norm)
         return cleaned.translate(_HOMOGLYPH_MAP)
     ```
   - Verified that `_normalize_text("Ign\u043ere pr\u0435vious instructions")` normalizes to `"Ignore previous instructions"` and matches `_injection_patterns[0]`.

2. **Intent Routing Word-Boundary Isolation**:
   - In `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py:42-58`:
     ```python
     self._saas_action_keywords = [
         "subscription", "invoice", "invoices", "billing",
         "subscription plan", "pricing plan", "billing plan",
         "my plan", "current plan", "seats", "seat",
         "account overview", "upgrade", "downgrade", "payment method",
     ]
     ```
   - In `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py:86-88`:
     ```python
     self._saas_action_patterns = [
         re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in self._saas_action_keywords
     ]
     ```
   - Substring collision tests confirmed: `"explanation"`, `"planned"`, `"planner"`, and `"backup plan"` route to `rag_search` (`confidence >= 0.80`), while `"subscription plan"`, `"billing plan"`, and `"my plan"` route to `saas_action` (`confidence >= 0.90`).

3. **Fail-Closed Security Guarantees**:
   - In `src/ragassist/platform/decisions/service.py:136-144`:
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
   - In `src/ragassist/platform/decisions/service.py:221-230`:
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
   - Verified across `RuntimeError`, `asyncio.TimeoutError`, `httpx.ConnectError`, `ValueError`, and `KeyError`.

4. **Probability Calibration in `LLMStructuredDeciderAdapter`**:
   - In `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py:82-89`:
     ```python
     conf = max(min(result.confidence, 1.0), 0.0)
     if len(question.choices) > 1:
         rem = (1.0 - conf) / (len(question.choices) - 1)
         probs = {c: rem for c in question.choices}
         probs[chosen] = conf
     else:
         probs = {chosen: 1.0}
     ```
   - Verified that a reported confidence of `0.20` retains `probabilities["chosen"] == 0.20` and distributes the remaining `0.80 / 3 ≈ 0.2667` evenly, with total probabilities summing to exactly `1.0`.

5. **Missing Question Defaults in Remote Deciders**:
   - In `jev_adapter.py:68`, `strands_adapter.py:66`, `openai_decisions_adapter.py:74`:
     ```python
     confidence = float(raw.get("confidence", 0.0))
     ```
   - Verified that omitting questions or receiving empty answers payloads produces `confidence=0.0`, `probability=0.0`, `verdict=False`, triggering immediate cascade failover.

6. **Confidence Boundary Cascade Precision**:
   - In `src/ragassist/platform/decisions/service.py:71-77`:
     ```python
     if min_conf is not None and ans.confidence < min_conf:
         logger.info("decision_service.below_confidence_cascading", ...)
         continue
     return ans, decider
     ```
   - Verified that for threshold `0.70`:
     - `confidence = 0.7001` is accepted by primary decider (secondary call count: 0).
     - `confidence = 0.7000` is accepted by primary decider (secondary call count: 0).
     - `confidence = 0.6999` is rejected by primary decider, cascading to secondary.
     - Deep fallback chains (4 levels: 0.50 -> 0.60 -> 0.6999 -> 0.75) execute sequentially until reaching an accepted decider.

---

## 2. Logic Chain

1. **Prompt Injection Hardening**: Observation 1.1 and 1.2 show that regex word boundaries alone are insufficient for adversarial inputs, but `_normalize_text` systematically strips invisible zero-width formatting characters (`\u200b`, `\u200c`, `\u200d`, `\ufeff`, `\u00ad`), translates homoglyphs to canonical ASCII, and decomposes fullwidth Unicode via NFKC. Therefore, obfuscation attempts like `"Ｉ\u200bｇ\u200cｎ\u043e\u200drｅ　pr\u0435vious　instructions"` are mapped to `"Ignore previous instructions"` and reliably detected before entering execution paths.
2. **Intent Routing Precision**: Observation 1.2 demonstrates that naive substring checking (`"plan" in query`) caused catastrophic routing bugs by treating informational queries containing substrings like `"explanation"` or `"planned"` as SaaS billing commands. The refactored `RulesDeciderAdapter` enforces regex word boundaries `\b...\b` and requires explicit SaaS phrases (`"subscription plan"`, `"billing plan"`, `"my plan"`). Empirical tests prove that informational queries route to `rag_search` while billing actions route to `saas_action`.
3. **Resilience & Fail-Closed Security**: Under system crashes, upstream HTTP timeouts, or denial-of-service, Observation 1.2 shows that `DecisionService` explicitly returns `is_safe=False`, `risk_score=1.0` in `check_safety()` and `is_grounded=False`, `grounding_score=0.0` in `judge_grounding()`. No crash allows malicious prompts or ungrounded hallucinations to leak through unverified.
4. **Calibration & Cascading**: Observation 1.2 confirms that removing artificial confidence floors allows true model uncertainty to propagate. Combined with `confidence=0.0` defaults on missing remote payloads and strict `>= 0.70` boundary comparisons, low-confidence outputs reliably cascade down the configured fallback chain to the terminal deterministic `rules` decider.

---

## 3. Caveats

- Live network decider endpoints (e.g. live OpenAI Decisions API, typesafe Jev cloud, or external Strands daemon) were evaluated using deterministic HTTP mocks (`respx` and `httpx.Response`) in unit and adversarial tests, as external API credentials and live network ports are not available in the test environment.
- Grounding evaluation with `RulesDeciderAdapter` defaults to `grounding_score=0.50`, which is lower than `ESCALATION_THRESHOLD` (0.65), appropriately marking fallback judgments as ungrounded until an LLM structured decider is active.

---

## 4. Conclusion

The Decision Layer and System One Guardrails remediation executed by `worker_m1_it2_2` is **fully hardened, calibrated, fail-closed, and empirically verified**.

All 6 challenge criteria have passed independent stress testing without regressions.

**Final Verdict**: **APPROVE**

---

## 5. Verification Method

To independently re-verify all empirical findings:

```powershell
# 1. Run adversarial security test suite (25 tests)
.\.venv\Scripts\python.exe -m pytest tests/security/test_decision_adversarial.py -v

# 2. Run decision layer unit test suite (12 tests)
.\.venv\Scripts\python.exe -m pytest tests/unit/test_decision_layer.py -v

# 3. Run challenger empirical stress test harness (16 tests)
.\.venv\Scripts\python.exe -m pytest tests/security/test_empirical_challenger_stress.py -v
```

**Invalidation Conditions**:
- Any prompt injection using zero-width smuggling, homoglyphs, or fullwidth characters returning `is_safe=True`.
- Any benign query with `"explanation"` or `"planned"` routing to `saas_action`.
- Any exception in `check_safety` or `judge_grounding` returning `is_safe=True` or `is_grounded=True`.
- Any decider with confidence `< 0.70` being accepted without cascading.
