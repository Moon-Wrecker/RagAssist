# Configure LLM providers and fallbacks

**Type:** How-to · **Audience:** an operator or developer who chooses the models · **Verified against:** `a989287`

**In plain English:** This page shows how to pick the models that RagAssist uses and the models that it tries when
the first one fails. You change a few lines in `.env`. You do not change code. The page ends with a check that shows
the chain that the system built.

## Goal

Run the assistant on a chosen provider (here: Gemini, with Claude as the fallback) and know what happens when a
provider fails.

## Before you start

- You know the terms [fallback chain](../glossary.md), role and alias. A role is a job such as `generator`. An alias is a
  short name for a model, such as `gemini-flash`.
- You have a key for each provider that you want to use.
- You read the [models catalog](../reference/models-catalog.md). It lists the roles, the models and the aliases.
- The stack runs (see [run the stack locally](../tutorials/01-run-the-stack-locally.md)).

> **WARNING.** Provider keys are secrets. Put them in `.env` only. Never put a key in `config/models.yaml`, a test or a
> document.

## Steps

1. Open `.env`.
2. Set the key of each provider that you use, for example `GEMINI_API_KEY` and `ANTHROPIC_API_KEY`. Paste your own
   values.
3. Choose the primary model of each role with the `LLM_ROLE_*` settings. This example uses Gemini:

   ```dotenv
   LLM_ROLE_GENERATOR_PRIMARY=gemini-flash
   LLM_ROLE_GENERATOR_FALLBACKS=claude-haiku
   LLM_ROLE_REWRITER_PRIMARY=gemini-flash-lite
   LLM_ROLE_AGENT_PRIMARY=gemini-flash
   LLM_ROLE_JUDGE_PRIMARY=gemini-flash-lite
   LLM_ROLE_DECIDER_FALLBACK=gemini-flash-lite
   ```

   Each value is a model key or an alias from `config/models.yaml`.

4. Know what each setting does:

   | Setting | Effect |
   |---|---|
   | `LLM_ROLE_GENERATOR_PRIMARY` | The first model for answers |
   | `LLM_ROLE_GENERATOR_FALLBACKS` | A comma list. It **replaces all** the fallbacks of the generator |
   | `LLM_ROLE_REWRITER_PRIMARY`, `LLM_ROLE_AGENT_PRIMARY`, `LLM_ROLE_JUDGE_PRIMARY` | The first model of that role. The fallbacks stay as in the file |
   | `LLM_ROLE_DECIDER_FALLBACK` | Sets the primary of the `decider` role, in spite of the name |

   > **NOTE.** Only the fallbacks of the generator have an environment setting. To change the fallbacks of another
   > role, edit the `roles` section of `config/models.yaml`.

5. Know the special setting `OPENAI_COMPATIBLE_MODEL`. When it is set, it overrides **all** roles with one model on the
   OpenAI-compatible endpoint. Leave it empty if you want the roles above to work.
6. Save `.env`.
7. Recreate the containers that read the settings:

   ```bash
   docker compose up -d --force-recreate api worker
   ```

8. Ask a question in Chat. Check the answer.

## Check

With a Gemini key, the example above builds these chains (checked with a read-only script at this commit):

| Role | Chain, first to last |
|---|---|
| generator | `gemini-flash-latest`, `claude-haiku-5-5` |
| rewriter, judge, decider | `gemini-flash-lite-latest`, `claude-haiku-5-5` |
| agent | `gemini-flash-latest`, `claude-sonnet-5-5` |

The generate step tries each model in order. If every model fails, the step re-raises the last error.

To list the real chains on your machine, run a read-only script from the repository root with your `.env` present.
Unverified: there is no committed command that prints the chains. The function `catalog_for` in
`src/ragassist/runtime.py` builds the catalog and applies the overrides.

## How the system behaves when a provider is missing

- A provider with no key is **dropped from fallbacks**. The catalog sets `skip_when_unconfigured: true` for it. This is
  true for Gemini.
- A provider with no key that you name as a **primary** stays in the chain. It sends the placeholder key
  `unconfigured`, fails and the chain moves on. Set the key, or name another primary.
- Retired model ids return 404. The names `claude-3-5-sonnet-20241022` and `claude-3-5-haiku-20241022` stay in the file
  only so that old configs resolve. Do not choose them.

## The deciders also use models

The decision layer picks up to three models for the `llm_structured`, `llm_structured_2` and `llm_structured_3` deciders.
It takes the decider chain first, then the generator chain, removes duplicates and stops at three. The values in
`.env.example` are:

- `DECIDER_CHAIN=openai_decisions,jev,llm_structured,llm_structured_2,rules`
- `ROUTER_DECIDER_CHAIN=semantic_router,openai_decisions,llm_structured,llm_structured_2,rules`

> **CAUTION.** Keep `rules` at the end of each chain. If you remove it and every model fails, the safety check fails
> closed and the assistant refuses questions with the text "I could not run the safety check just now, so I cannot
> answer yet. Please try again in a moment."

> **CAUTION.** `DECIDER_TIMEOUT_MS` is 8000 in `.env.example`. A value that is too low makes every member time out. The safety
> check then fails closed.

## Troubleshooting

- The log shows a model error, then the answer uses another model. This is the fallback chain at work.
- Every answer fails with 401 or an authentication error. The key in `.env` is wrong or empty. Recreate the containers
  after a fix.
- A new model name is "unknown". Add it to `config/models.yaml`, or use an alias. See
  [add an LLM provider](add-an-llm-provider.md).
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Configuration reference, section 10](../reference/configuration.md#10-llm-role-overrides)
- [ADR 0004: decision layer](../adr/0004-decision-layer.md) and [ADR 0013: Gemini provider](../adr/0013-gemini-provider.md)
