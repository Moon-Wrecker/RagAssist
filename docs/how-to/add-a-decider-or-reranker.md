# Add a decider or a reranker

**Type:** How-to · **Audience:** a backend developer who extends the decision layer or the search ranking · **Verified against:** `a989287`

**In plain English:** A [decider](../glossary.md) answers small questions for the assistant: is this input safe, where
should this question go, is this passage relevant. A [reranker](../glossary.md) sorts the passages that the search
found. Both are ports, so you add a new one as an adapter and give it a name in a chain. This page shows both jobs.

## Goal

Add a new decider adapter or reranker adapter, name it in the chain setting and prove it with the shared contract tests.

## Before you start

- You know the terms [decider chain](../glossary.md), [confidence gate](../glossary.md) and
  [fail closed](../glossary.md).
- You read [ADR 0004: decision layer](../adr/0004-decision-layer.md), [ADR 0005: reranker chain](../adr/0005-reranker-chain.md)
  and the [ports and adapters reference](../reference/ports-and-adapters.md).
- Before you code, write the goal in one or two sentences. Read the documents of every library that you use. Prefer a
  proven library to custom code. Record what you read in the docstring of the adapter or in an ADR
  (`AGENTS.md`, section 3.5).

> **WARNING.** CPU-bound work (a local model, ONNX, tokenization) must not run in the event loop. Run it with
> `asyncio.to_thread()` through the bounded executor in `src/ragassist/shared/resilience.py`.

## Part A: add a decider

1. Make the file `src/ragassist/platform/decisions/adapters/<name>_adapter.py`.
2. Write a class that has the five members of the `Decider` port in `src/ragassist/platform/decisions/ports.py`:

   | Member | Job |
   |---|---|
   | `name` (property) | The adapter name |
   | `decide(input_text, questions)` | Answers a batch of questions in one pass |
   | `evaluate_choice(input_text, question)` | Picks one option and gives a confidence |
   | `evaluate_predicate(input_text, question)` | Answers a yes or no question with a probability |
   | `evaluate_score(input_text, question)` | Gives an ordinal rating |

3. Raise an error when you cannot decide. Do not invent a verdict. The shipped `llm_structured` decider raises for a
   failed predicate or score, so that the chain moves to the next member.
4. Register the adapter in `build_decider_registry` in `src/ragassist/platform/decisions/service.py`:

   ```python
   registry.register("my_decider", lambda: MyDeciderAdapter(settings=cfg))
   ```

5. Add the name to a chain in `.env`. The settings are `DECIDER_CHAIN` and `ROUTER_DECIDER_CHAIN`. The values in `.env.example` are
   `openai_decisions,jev,llm_structured,llm_structured_2,rules` and
   `semantic_router,openai_decisions,llm_structured,llm_structured_2,rules`. The first member is tried first. A member
   whose confidence is below the minimum, or that fails or times out, hands over to the next member.

   > **CAUTION.** Keep `rules` last. It is the member that works with no model. Without it, a total model outage makes the
   > safety check fail closed and the assistant refuses questions.

6. If the adapter needs a setting, add the field to `src/ragassist/shared/config/settings.py` and update
   `.env.example` in the same change. A key has the default empty string. Add a secret to the masked lists in the
   settings `__repr__` and `model_dump_json`.
7. Write the tests:

   - Use the `DeciderContract` in `tests/support/contracts/decider.py`. It checks the port behavior.
   - Add unit tests in `tests/unit/platform/decisions/`.
   - The tests in `tests/selfcheck` prove that the fakes still match the contract.

## Part B: add a reranker

1. Make the file `src/ragassist/platform/rerank/adapters/<name>_adapter.py`.
2. Write a class with the `Reranker` port of `src/ragassist/platform/rerank/ports.py`: a `name` property and

   ```python
   async def rerank(self, query: str, candidates: list[Candidate], *, top_n: int) -> list[Scored]: ...
   ```

   Return at most `top_n` items, sorted by score from high to low.
3. Add a branch for the name in `build_reranker_chain` in `src/ragassist/platform/rerank/service.py`. The function is an
   `if` and `elif` list on the chain names. The existing names are `none`, `cross_encoder`, `flashrank` and `api`. Wrap the
   import in a `try` block that logs a warning, as the other branches do. The chain then skips the member when the library
   is missing.
4. Name it in `.env` with `RERANKER_CHAIN`, for example `my_reranker,flashrank,none`. The chain tries members in order. If
   every member fails to build, the code adds the no-op reranker.
5. Know the limit. The `decision` reranker exists as an adapter, but `build_reranker_chain` does not build it from the
   chain names. It works only when a caller passes it in the `instances` argument. A new reranker that you want in
   `RERANKER_CHAIN` needs its own branch, as in step 3.
6. Add settings for the model, the URL or the key as normal settings fields, with `.env.example` updated in the same
   change. Do not read them with `getattr` as the `api` branch does for `RERANK_API_*`.
7. Write the tests: the `RerankerContract` in `tests/support/contracts/reranker.py` and unit tests in
   `tests/unit/platform/rerank/`.

## Check

- `pytest tests/unit/platform/decisions tests/unit/platform/rerank tests/selfcheck` passes. See
  [run the tests](run-the-tests.md).
- `lint-imports` exits with 0. A platform adapter must follow the layer rules.
- The tests in `tests/hygiene/test_env_example.py` pass. They check that `.env.example` matches the settings.
- Start the API with the new chain name. The log shows no `reranker.unknown_name_skipped` warning and no
  "unavailable" warning for your adapter.

## Troubleshooting

- The log shows `reranker.unknown_name_skipped`. The chain name has no branch in `build_reranker_chain`, or it has a
  typo. Chain names are lower case.
- A decider name in the chain does nothing. It is not registered in `build_decider_registry`.
- Every question is refused after your change. The safety check failed closed. Check `DECIDER_TIMEOUT_MS` (8000 in
  `.env.example`) and keep `rules` in the chain.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Configuration reference](../reference/configuration.md)
- [Assistant graph](../reference/assistant-graph.md)
- [Ports and adapters](../reference/ports-and-adapters.md)
