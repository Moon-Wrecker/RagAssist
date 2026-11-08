# ADR 0004: Decision Layer First with Calibrated Probabilities

## Context & Problem
Using large generative models (like GPT-4) for routine query classification, safety gating, and chunk grading incurs significant latency (multi-second delays), excessive token costs, and non-deterministic formatting failures.

## Decision
We architect a dedicated **Decision Layer** using "System One" decision models (Jev, OpenAI Decisions API, Strands Decider) that evaluate state against structured questions (`Choice`, `Score`, `Predicate`) and return calibrated probabilities without text generation.

A confidence-gated fallback chain (`semantic-router` → `openai_decisions` → `jev` → `llm_structured`) ensures high throughput and zero disruption if a specific decision provider is offline.

## Consequences
- **Positive:** Sub-100ms routing decisions and accurate chunk relevance gating.
- **Positive:** Calibrated probabilities allow clear confidence thresholds for human escalation triggers.

