# Gate Status — Milestone 1: Model & Decision Platform

## Gate — Iteration 1
| Agent | Role | Verdict | Source |
|---|---|---|---|
| worker_m1_2 | teamwork_worker | DONE (309 unit tests passed, 0 failed; 30/30 E2E passed) | handoff.md |
| reviewer_m1_1 | teamwork_reviewer | REQUEST_CHANGES | handoff.md |
| reviewer_m1_2 | teamwork_reviewer | APPROVE | handoff.md |
| challenger_m1_1 | teamwork_challenger | APPROVE (41 adversarial tests passed) | handoff.md |
| challenger_m1_2 | teamwork_challenger | REQUEST_CHANGES (25 adversarial tests passed; found 5 defect items) | handoff.md |
| auditor_m1_1 | teamwork_auditor | CLEAN | handoff.md |

Gate Result: **FAIL** (Reviewer 1 and Challenger 2 requested changes; proceeding to Iteration 2 remediation)

### Action Items for Iteration 2
1. **`RulesDeciderAdapter` Intent Misrouting & Unicode Normalization**:
   - In `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py`:
     - Replace naive substring matching `k in lower` with regex word boundaries `re.search(rf"\b{re.escape(k)}\b", lower)` so `"plan"` does not match `"explanation"`, `"planned"`, etc.
     - Add `unicodedata.normalize("NFKC", ...)` prior to regex evaluation to prevent zero-width space smuggling and homoglyphs.
2. **Remove ProactorEventLoop Monkeypatch from Production Code**:
   - In `src/ragassist/shared/config/settings.py`:
     - Delete lines 11–43 (the ProactorEventLoop monkeypatch).
     - Relocate any needed Windows test runner socket patches strictly to `tests/conftest.py`.
3. **Resolve Role Shadowing in `settings.py` (DEFECT-14)**:
   - In `src/ragassist/shared/config/settings.py`:
     - Change default values of `LLM_ROLE_*` (e.g., `LLM_ROLE_REWRITER_PRIMARY: str = ""`, `LLM_ROLE_JUDGE_PRIMARY: str = ""`, etc.) to empty strings `""` or `None`, so `models.yaml` serves as the single authoritative source of truth unless explicitly overridden in `.env`.
4. **Model Capabilities & Metadata Consistency (DEFECT-17)**:
   - Align context windows and pricing in `src/ragassist/platform/llm/adapters/openrouter_adapter.py` and `openai_compatible_adapter.py` with `config/models.yaml` (e.g. `openrouter-llama-3.1-70b` context window = 131,072, `local-llama-3.1-8b` = 32,768).
5. **Harden Fail-Open Security & Grounding Fallbacks (Fail-Closed)**:
   - In `src/ragassist/platform/decisions/service.py`:
     - `check_safety`: In `except Exception as exc:`, return `is_safe=False`, `risk_score=1.0`, `violation_categories=["safety_check_error"]`, `reasoning=f"Fail-closed on check failure: {exc}"`.
     - `judge_grounding`: In `except Exception as exc:`, return `is_grounded=False`, `grounding_score=0.0`, `unsupported_claims=[f"Grounding evaluation failed: {exc}"]`, `confidence=0.0`, `reasoning=f"Fail-closed on evaluation failure: {exc}"`.
6. **Fix Probability Distortion in `LLMStructuredDeciderAdapter`**:
   - In `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py`:
     - Line 83: replace `probs[chosen] = max(result.confidence, 0.70)` with `probs[chosen] = max(result.confidence, 0.05)`.
7. **Fix Missing Question Field Default in Decider Adapters**:
   - In `jev_adapter.py:68`, `strands_adapter.py:66`, and `openai_decisions_adapter.py:74`:
     - Change `raw.get("confidence", 0.8)` to `raw.get("confidence", 0.0)` so missing question answers in external API responses are not falsely accepted as high confidence.
