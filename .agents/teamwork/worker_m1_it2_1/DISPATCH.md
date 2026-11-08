## 2026-11-07T21:42:57Z
You are Milestone 1 Iteration 2 Worker (Platform & Decision Layer Remediation Implementer).

Working directory: d:\Coding\RagAssist-1
State folder: d:\Coding\RagAssist-1\.agents\teamwork\worker_m1_it2_1

MANDATORY FIRST STEP:
Read the following files before writing any code:
1. `d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md` (Verbatim user request)
2. `d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md` (Master architecture index & contracts)
3. `d:\Coding\RagAssist-1\.agents\teamwork\orchestrator_1\GATE_STATUS.md` (Gate review status and required fixes)
4. `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_it2_1\analysis_decision_remediation.md` (Decision layer remediation specification)
5. `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_it2_2\analysis_settings_catalog_remediation.md` (Settings, Asyncio & Catalog remediation specification)
6. `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_it2_3\analysis_adapters_test_harmonization.md` (Adapter capabilities & test harmonization specification)

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Exclusive Write Ownership:
- `src/ragassist/platform/decisions/`
- `src/ragassist/shared/config/settings.py`
- `tests/conftest.py`
- `src/ragassist/platform/llm/`
- `config/models.yaml`
- `.env.example`
- `tests/unit/platform/llm/`
- `tests/security/test_decision_adversarial.py`
- `tests/unit/test_decision_layer.py`

Tasks to Execute (follow the line-by-line diffs in the 3 Explorer analysis files):
1. **Decision Layer Remediation (from `analysis_decision_remediation.md`)**:
   - `RulesDeciderAdapter`: Add `_normalize_text` (NFKC normalization, zero-width space filtering, homoglyph mapping) and word-boundary regexes `\b{k}\b` for intent keywords (`"plan"` isolated from `"explanation"`).
   - `DecisionService`: Fail-closed hardening in `check_safety` (`is_safe=False`, `risk_score=1.0`, `violation_categories=["safety_check_error"]`) and `judge_grounding` (`is_grounded=False`, `grounding_score=0.0`, `confidence=0.0`).
   - `LLMStructuredDeciderAdapter`: Replace line 83 clamp with calibrated `max(result.confidence, 0.05)`.
   - Remote Deciders (`jev_adapter.py`, `strands_adapter.py`, `openai_decisions_adapter.py`): Set missing question confidence to `0.0`.
   - Update `tests/unit/test_decision_layer.py` with the 3 regression prevention tests.
2. **Settings, Asyncio & Role Catalog Remediation (from `analysis_settings_catalog_remediation.md`)**:
   - `src/ragassist/shared/config/settings.py`: Delete lines 11–43 (proactor monkeypatch). Update all `LLM_ROLE_*` string defaults to empty string `""` (fixes DEFECT-14).
   - `tests/conftest.py`: Add the Win32 IOCP completion-port self-pipe patch so Windows test executions run hermetically.
   - `src/ragassist/platform/llm/catalog.py`: Update `resolve_role_chain` with `.strip()` guards so empty settings do not shadow `models.yaml`.
   - `.env.example`: Synchronize role override keys with empty values.
   - `tests/unit/platform/llm/test_catalog.py`: Remove `@defect("DEFECT-14")` so `test_default_settings_do_not_shadow_the_yaml_roles` actively passes.
3. **Adapter Capabilities & Test Harmonization (from `analysis_adapters_test_harmonization.md`)**:
   - `openrouter_adapter.py`: Add Mistral Large pricing ($2.00/$6.00), Llama 3.1 70B context window (131,072), Llama 3.1 8B context window (32,768).
   - `config/models.yaml`: Set `capabilities.json_mode: false` for OpenRouter models.
   - Create `src/ragassist/platform/llm/adapters/openai_compatible_adapter.py` wrapper and update `__init__.py`.
   - `tests/unit/platform/llm/test_llm_service.py`: Remove `@defect("DEFECT-17")` from line 204 so `test_all_providers_agree` actively passes.
   - `tests/security/test_decision_adversarial.py`: Harmonize the 5 defect observation test assertions to verify the hardened, fail-closed behavior.

Verification Requirements:
- Execute commands using `run_command` with `BypassSandbox=True`.
- Run:
  1. `.\.venv\Scripts\python.exe -m pytest tests/unit/platform/llm/test_catalog.py -k "test_default_settings_do_not_shadow_the_yaml_roles" -v`
  2. `.\.venv\Scripts\python.exe -m pytest tests/unit/platform/llm/test_llm_service.py -k "test_all_providers_agree" -v`
  3. `.\.venv\Scripts\python.exe -m pytest tests/unit/test_model_catalog.py tests/unit/test_embedding_providers.py tests/unit/test_decision_layer.py tests/unit/test_shared_kernel.py -v`
  4. `.\.venv\Scripts\python.exe -m pytest tests/security/test_decision_adversarial.py tests/unit/test_adversarial_m1.py -v`
  5. `.\.venv\Scripts\python.exe -m pytest tests/unit/ -v`
  6. `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier1_features.py -v`
- Document all file modifications in `d:\Coding\RagAssist-1\.agents\teamwork\worker_m1_it2_1\changes.md`.
- Deliver a 5-component `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\worker_m1_it2_1\` and notify orchestrator via `send_message`.
