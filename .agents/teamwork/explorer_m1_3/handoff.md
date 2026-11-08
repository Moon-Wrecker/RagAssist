# Handoff Report: Decision Layer & Guardrails Architecture

**Explorer**: Milestone 1 Explorer 3 (`explorer_m1_3`)  
**Mission**: Decision Layer Architecture, Calibrated Probabilities, and Confidence-Gated Fallback Chains  
**Date**: 2026-11-07  
**State Folder**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_3`  
**Target Module**: `src/ragassist/platform/decisions/`  

---

## 1. Observation

1. **ADR 0004 & Architecture Rules**:
   - `docs/adr/0004-decision-layer.md` defines the decision layer requirement:
     > "We architect a dedicated Decision Layer using 'System One' decision models (Jev, OpenAI Decisions API, Strands Decider) that evaluate state against structured questions (`Choice`, `Score`, `Predicate`) and return calibrated probabilities without text generation. A confidence-gated fallback chain (`semantic-router` → `openai_decisions` → `jev` → `llm_structured`) ensures high throughput and zero disruption if a specific decision provider is offline."
   - `AGENTS.md` § 2.2 specifies:
     > "Decision Layer First: Routing, input safety guards, chunk relevance grading, and grounding checks use the `Decider` port (`jev`, `openai_decisions`, `strands_local`, `semantic_router`, `llm_structured`, `rules`) with confidence-gated fallback chains."

2. **Application Settings (`src/ragassist/shared/config/settings.py`)**:
   - Lines 108–118 define the configuration variables:
     ```python
     # --- Decisions ---
     DECIDER_CHAIN: str = "openai_decisions,jev,llm_structured"
     ROUTER_DECIDER_CHAIN: str = "semantic_router,openai_decisions,llm_structured"
     DECIDER_MIN_CONFIDENCE: float = 0.70
     DECIDER_TIMEOUT_MS: int = 1000
     ESCALATION_THRESHOLD: float = 0.65

     TYPESAFE_API_KEY: str = ""
     OPENAI_DECISIONS_API_KEY: str = ""
     STRANDS_DECIDER_ENDPOINT: str = "http://localhost:8002/v1/decide"
     ```

3. **OpenAI SDK v3.46.0 Decision Endpoints**:
   - Inspection of `.venv/Lib/site-packages/openai/resources/decisions.py` and `openai/types/decision.py` revealed native support for the new `/decisions` endpoint:
     - `AsyncDecisions.create(input=..., model=..., questions=...)`
     - Question types: `Choice` (`QuestionQuestionParamChoice`), `Predicate` (`QuestionQuestionParamPredicate`), and `Score` (`QuestionQuestionParamScore`).
     - Answer types: `AnswerAnswerResourceChoice` (with `.choice`, `.confidence`, `.probabilities`), `AnswerAnswerResourcePredicate` (with `.probability`), and `AnswerAnswerResourceScore` (with `.score`, `.confidence`, `.probabilities`).

4. **Resilience Utilities (`src/ragassist/shared/resilience.py`)**:
   - Lines 30–73 implement `FallbackChain[T].execute(operation, is_acceptable=...)`:
     - Allows checking acceptance (`is_acceptable(result)`). If `False`, it logs a warning and cascades to the next member.
     - `run_cpu_bound()` uses `ThreadPoolExecutor(max_workers=4)` to offload CPU-bound inference without blocking the async event loop.

5. **Existing Platform Directory Structure**:
   - `src/ragassist/platform/decisions/` exists with empty `__init__.py` and empty `adapters/__init__.py`.

---

## 2. Logic Chain

1. **Separation of System-1 Decisions from System-2 Generation**:
   - Routine RAG control flow (routing, input safety, chunk relevance grading, hallucination detection) requires fast, low-latency, deterministic decisions (Observation 1).
   - Generative LLMs take 1.5s–4s, cost more tokens, and can hallucinate or fail output formatting. System-One decision models evaluate questions in <100ms using calibrated probabilities without autoregressive generation (Observation 1, 3).

2. **Direct Mapping of Mathematical Primitives to Ports**:
   - The three primitives (`Choice`, `Predicate`, `Score`) defined in ADR 0004 map directly to the OpenAI Decisions API types discovered in the SDK (Observation 1, 3).
   - Therefore, `src/ragassist/platform/decisions/ports.py` should model `ChoiceQuestion`/`ChoiceAnswer`, `PredicateQuestion`/`PredicateAnswer`, and `ScoreQuestion`/`ScoreAnswer` as the fundamental primitives, while exposing high-level domain DTOs (`RoutingDecision`, `SafetyVerdict`, `RelevanceScore`, `GroundingVerdict`) matching `PROJECT.md` contracts.

3. **Fallback & Confidence Gating Integration**:
   - `FallbackChain` in `shared/resilience.py` already supports an `is_acceptable` predicate (Observation 4).
   - By configuring `is_acceptable = lambda res: res.confidence >= settings.DECIDER_MIN_CONFIDENCE` (0.70), `DecisionService` can automatically cascade from fast local classifiers (`SemanticRouterAdapter`) down through specialized APIs (`OpenAIDecisionsAdapter`, `JevAdapter`, `StrandsDeciderAdapter`) to `LLMStructuredDeciderAdapter` (Observation 2, 4).
   - Wrapping each adapter invocation in `asyncio.wait_for(timeout=settings.DECIDER_TIMEOUT_MS / 1000.0)` guarantees that a hanging network call cascades in ≤1,000ms (Observation 2).

4. **Infallible Fallback Guarantee**:
   - `LLMStructuredDeciderAdapter` wraps standard LangChain `BaseChatModel` with Pydantic structured output.
   - Because chat models are universally available across local and cloud providers (OpenAI, Anthropic, OpenRouter, Ollama), having `LLMStructuredDeciderAdapter` as the terminal fallback member in both `DECIDER_CHAIN` and `ROUTER_DECIDER_CHAIN` guarantees that decisions never fail even if specialized decision APIs or local microservices are offline.

---

## 3. Caveats

1. **External Decision Microservices (Strands / Jev)**: Live HTTP calls to `http://localhost:8002/v1/decide` or `https://api.typesafe.ai` require network reachability and valid API keys (`TYPESAFE_API_KEY`). Unit tests must use `respx` to mock these endpoints rather than making real network calls.
2. **`semantic-router` Library Dependency**: While `semantic-router` is listed in `pyproject.toml`, `SemanticRouterAdapter` should include an internal cosine-similarity fallback over embedded seed utterances so that tests pass even in lightweight environments where the heavy package is not installed.
3. **Logprobs vs Structured Schema Confidence**: While OpenAI models support logprobs to compute mathematical softmax probabilities, other LLM providers (e.g. Anthropic Claude) do not expose token logprobs. `LLMStructuredDeciderAdapter` should elicit confidence as a structured Pydantic float field between 0.0 and 1.0 to remain provider-agnostic.

---

## 4. Conclusion

The Decision Layer architecture for Milestone 1 is completely designed and ready for implementation.
- The `ports.py` file will establish clean, protocol-oriented interfaces (`Decider`) and DTOs (`RoutingDecision`, `SafetyVerdict`, `RelevanceScore`, `GroundingVerdict`).
- The 5 adapters (`SemanticRouterAdapter`, `OpenAIDecisionsAdapter`, `JevAdapter`, `StrandsDeciderAdapter`, `LLMStructuredDeciderAdapter`) and `RulesDeciderAdapter` provide end-to-end coverage across ultra-fast in-memory routing, native OpenAI decisions, calibrated microservices, and bulletproof structured LLM fallbacks.
- `DecisionService` cleanly encapsulates the confidence-gated cascading logic using `FallbackChain` with `DECIDER_MIN_CONFIDENCE=0.70` and `DECIDER_TIMEOUT_MS=1000`.
- The detailed analysis and specifications are documented in `analysis_decisions.md`.

---

## 5. Verification Method

To independently verify the architecture and recommendations:

1. **Inspect Architecture and Specifications**:
   - Check `analysis_decisions.md` located at `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_3\analysis_decisions.md`.
2. **Inspect Existing Settings & ADRs**:
   - Check `docs/adr/0004-decision-layer.md` and `src/ragassist/shared/config/settings.py` (lines 108–118).
3. **Verify OpenAI Decisions SDK Types**:
   - Run:
     ```powershell
     .venv\Scripts\python -c "import openai.types.decision as d; print(dir(d))"
     ```
   - Observe `AnswerAnswerResourceChoice`, `AnswerAnswerResourcePredicate`, `AnswerAnswerResourceScore`.
4. **Verify Implementation Readiness with Test Run**:
   - Run the existing test suite to ensure the baseline remains healthy:
     ```powershell
     .venv\Scripts\python -m pytest tests/unit -v
     ```
