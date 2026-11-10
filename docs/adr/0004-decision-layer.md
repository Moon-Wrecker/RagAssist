# ADR 0004: Decision Layer First with Calibrated Probabilities

## Context & Problem
Using large generative models (like GPT-4) for routine query classification, safety gating, and chunk grading incurs significant latency (multi-second delays), excessive token costs, and non-deterministic formatting failures.

## Decision
We architect a dedicated **Decision Layer** using "System One" decision models (Jev, OpenAI Decisions API, Strands Decider) that evaluate state against structured questions (`Choice`, `Score`, `Predicate`) and return calibrated probabilities without text generation.

A confidence-gated fallback chain (`semantic-router` → `openai_decisions` → `jev` → `llm_structured`) ensures high throughput and zero disruption if a specific decision provider is offline.

## Consequences
- **Positive:** Sub-100ms routing decisions and accurate chunk relevance gating.
- **Positive:** Calibrated probabilities allow clear confidence thresholds for human escalation triggers.


## Amendment: model failures move to the next model, then to the rules

Found when the safety check refused ordinary questions again and again ("I could not run the safety check just now"):

- The LLM-backed decider answered a failed safety call with an invented "unsafe, probability 0.5" verdict instead of an
  error. The fallback chain therefore never reached the next decider, and a person was told their question broke a
  rule. The adapter now raises on a failed predicate or score, so the chain moves on. A failed choice (routing) still
  returns a low-confidence answer that the confidence gate rejects.
- A chain with one LLM decider has one point of failure: a provider outage, a rate limit or a slow reply ends the
  turn. There is now one LLM decider per model (`llm_structured`, `llm_structured_2`, `llm_structured_3`). The models
  come from the decider role, then the generator role (the normal LLM), without repeats, so a chain such as
  `llm_structured,llm_structured_2,rules` tries a second model before it uses the rules.
- Each LLM decider uses LangChain `max_retries=1`. The library default retries with back-off for longer than
  `DECIDER_TIMEOUT_MS`, which stopped the next decider from ever running.
- The rules decider stays the last member of the default chains. It is a small deterministic pattern check that needs
  no network, so a total model outage gives a weaker check (visible as `decider=rules` in the trace) and not a
  refusal. A deployment that prefers to refuse when no model can check the input removes `rules` from `DECIDER_CHAIN`;
  the check then fails closed as before.

The rules decider is a floor and not a complete defence against prompt injection. OWASP lists prompt injection as the
top risk for LLM applications and no classifier removes it. This system also relies on the layers behind the check:
tenant isolation with row-level security (ADR 0002), tool calls that need approval (ADR 0006) and a Principal that
never comes from model output.
