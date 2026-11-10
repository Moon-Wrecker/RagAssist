# The decision layer

**Type:** Explanation · **Audience:** engineers and reviewers who want to know why small decisions do not use the big model · **Verified against:** `a989287`

**In plain English:** An assistant turn must make many small decisions. Is the question safe? What kind of question is
it? Does this passage help? Is the answer backed by the passages? The project does not ask a large text model to write
a free-form reply for each of these. It asks a small, typed question and takes back a probability. This page explains
why, how the chain of fallbacks works, and what went wrong the first time.

## The idea

A [decider](../glossary.md) answers a typed question. The port in `src/ragassist/platform/decisions/ports.py` knows three
question types:

| Question type | Example | Answer |
|---|---|---|
| Choice | Which of the four routes fits this question? | One choice and a confidence |
| Predicate | Does this input contain prompt injection? | A verdict (yes or no) and a probability |
| Score | How complex is this question? | A number on ordered levels |

The answer is a number and not a paragraph. Code can compare a number with a threshold. Code cannot compare a paragraph.
[ADR 0004](../adr/0004-decision-layer.md) gives the reasons for this design:

- **Latency.** A routing choice that waits for a long model reply costs seconds. A classifier answers faster.
- **Cost.** A turn that searches the documents needs a safety check, a route, a complexity score, one relevance grade
  for each passage and a grounding check. [ADR 0015](../adr/0015-caching.md) counts about six model calls. Large-model
  prices add up.
- **Format failures.** A model that must write JSON sometimes writes something else. A typed question limits the answer.
- **Thresholds.** A calibrated probability gives a clear line for "send to a person".

The ADR calls these models "System One" decision models. See *System One decision model* in the
[glossary](../glossary.md).

## What the layer decides

The graph asks the decision layer five questions. `DecisionService` has a method for four of them. The `router` node asks
the complexity question itself, through `decider_chain` (`src/ragassist/modules/assistant/graph/nodes/router_node.py`).

| Operation | Used by | Question type |
|---|---|---|
| `route_query` | the `router` node | Choice |
| complexity score (not a `DecisionService` method) | the `router` node | Score |
| `check_safety` | the `guard_input` node | Predicate |
| `grade_chunk_relevance` | the `grade_relevance` node | Predicate |
| `judge_grounding` | the `verify_grounding` node | Predicate |

[How an answer is made](how-an-answer-is-made.md) shows where each one sits in the turn.

## Six adapters behind one port

The port `Decider` has several adapters. The registry builds them by name, and settings choose the order.

| Name | What it is |
|---|---|
| `openai_decisions` | A client for a hosted decision endpoint |
| `jev` | A client for the TypeSafe AI Jev decision service |
| `strands_local` | A client for a local decision micro-service |
| `semantic_router` | A local router. In this code it scores word overlap with example sentences. It answers choice questions only. |
| `llm_structured` and its numbered copies | A chat model forced to return a typed object. One decider exists for each model. |
| `rules` | Fixed patterns. It needs no network. |

Two facts about the weaker adapters:

- The `semantic_router` returns a fixed neutral answer for predicate and score questions. It belongs in the router
  chain and not in the general chain. The default chains follow this rule.
- The `rules` decider checks a list of injection patterns after it removes zero-width characters and maps common look-alike
  letters to plain ones. It routes with keyword lists. For predicates that it does not know, it returns a neutral
  answer with probability 0.5.

The adapters for hosted services call external APIs. The names of their keys are settings. Their values live in `.env`.

## The chain with a confidence gate

Each operation runs through a [fallback chain](../glossary.md). The class `FallbackChain` in
`src/ragassist/shared/resilience.py` tries the members in order. It moves on to the next member in three cases: the
member raises an error, the member is too slow, or the member's answer is not acceptable.

- **Too slow.** Each call has a time limit, `DECIDER_TIMEOUT_MS`.
- **Not acceptable.** For routing, an answer is acceptable only if its confidence reaches `DECIDER_MIN_CONFIDENCE`.
  The other operations accept any answer, because a probability is already the signal that they use.
- **Error.** Any exception moves the chain on.

There are two chains. `ROUTER_DECIDER_CHAIN` serves routing. `DECIDER_CHAIN` serves the rest, including the complexity
score. The sample `.env.example` ends both with `rules`. The file explains this in a comment.

If every member fails, the service does not crash the turn. It returns a default. The default differs by question.
This is the most important design choice of the layer.

| Question | Default when no decider answers | Why this default |
|---|---|---|
| Safety | Refuse (fail closed) | Letting an unchecked question through is the risky error. |
| Grounding | Not grounded (fail closed) | Showing an unchecked answer is the risky error. |
| Relevance of one passage | Relevant (fail open) | Dropping the only source is worse than keeping one extra passage. |
| Route | `rag_search` | A search reads and does not change anything. |
| Complexity | 2.0 | This selects the strong model tier. |

A fail-closed safety result carries the category `safety_check_error`. The guard node uses it to write a different
message: "I could not run the safety check just now". The system does not accuse the person of breaking a rule when the
check itself broke. The cache never stores this result.

## The lesson: a made-up verdict hid an outage

The ADR has an amendment that records a real incident. The safety check refused ordinary questions again and again.

The cause was in the adapter for the model-backed decider. When its model call failed, it returned an invented verdict:
"unsafe, probability 0.5". The chain saw a normal answer. It never moved to the next decider. A person was told that
their question broke a rule, when the provider was only down or slow.

Four changes fixed it. Each has a reason:

- **Raise, do not invent.** The adapter now raises an error on a failed predicate or score. The chain sees the failure
  and moves on. A failed choice still returns a low-confidence answer. The confidence gate rejects it, so the chain also
  moves on.
- **One decider for each model.** A chain with one model-backed decider has one point of failure. The registry now
  builds `llm_structured`, `llm_structured_2` and `llm_structured_3`. The models come from the decider role in
  `config/models.yaml`, then from the generator role, without repeats, with a limit of three. A chain such as
  `llm_structured,llm_structured_2,rules` tries a second model before it uses the rules.
- **A low retry count.** Each model-backed decider uses `max_retries=1`. The library default retries with a back-off
  that lasts longer than `DECIDER_TIMEOUT_MS`. The next decider then never got a turn.
- **A realistic time limit.** The comment in `.env.example` says that model-backed deciders need several seconds. A
  limit that is too small makes every member time out, the safety check fail closed and every question be refused. The
  sample value is 8000 ms.

The general lesson: a fallback chain works only if each member reports its own failure honestly. A member that hides
its failure turns the chain into a single point of failure.

## The floor and its limits

The `rules` decider is the last member of the default chains. It needs no network. When every model is down, the check
becomes weaker but the service still answers. The trace shows `decider=rules`, so an operator can see the downgrade.

The ADR is clear about the limits. The rules decider is a floor and not a complete defence against prompt injection.
No classifier removes this risk. The system relies on the layers behind the check: row-level security
([tenant isolation](tenant-isolation-defence-in-depth.md)), tool calls that need approval
([approvals and actions](approvals-and-actions.md)) and a Principal that never comes from model output.

A deployment that prefers to refuse when no model can check the input removes `rules` from `DECIDER_CHAIN`. The check
then fails closed.

One more effect follows from the same design. With only the rules decider available, a grounding check cannot pass. The
rules decider returns the neutral probability 0.5 for it, and the grounding rule asks for at least
`ESCALATION_THRESHOLD`. The answer is then "not grounded", and the turn escalates. This is a safe failure. It is also
visible to users, so operators should watch for `decider=rules` in traces.

## Trade-offs

| Choice | Benefit | Cost |
|---|---|---|
| Typed questions, not free text | Fast, cheap and easy to threshold | The decider cannot explain itself in depth |
| Hosted deciders first | Calibrated probabilities | A dependency on an outside service and its key |
| A model-backed decider as a universal fallback | Works with any chat model | Slower, and the probability is the model's own claim |
| `rules` as the floor | The system keeps working offline | A weaker check in an outage |
| Different defaults for each question | Each failure does the least harm | A reader must learn five defaults |

## Alternatives not chosen

- **One large model for every decision.** Simple to build. Slow and costly. ADR 0004 names this as the problem.
- **No safety check, only the model's own refusal.** The check also saves model cost when it blocks a question early.
- **Fail open for safety.** Rejected. The ADR amendment keeps the rule that an unchecked input is refused.

## Honest limits

- **Unverified: the complexity scale.** The complexity question names levels 1, 3 and 5. The model-backed adapter asks the
  model for a number from 0.0 to 1.0 (`StructuredScore` allows no more than 1.0). The tier rule treats a score below 2.0
  as the cheap tier. With that adapter every question therefore picks the cheap tier. This page did not run a live
  check. See
  [known limitations](known-limitations-and-roadmap.md).
- **Calibration is claimed, not measured here.** The test suite checks the injection floors on the rules decider. The
  model-backed decider has a live test with a higher floor. See [testing strategy](testing-strategy.md).

## Related pages

- [How an answer is made](how-an-answer-is-made.md)
- [Provider abstraction and fallbacks](provider-abstraction-and-fallbacks.md)
- [Ports and adapters reference](../reference/ports-and-adapters.md)
- [Add a decider or reranker](../how-to/add-a-decider-or-reranker.md)
- [Glossary](../glossary.md)
