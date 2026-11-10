# Add an LLM provider

**Type:** How-to · **Audience:** a backend developer who connects a new model service · **Verified against:** `a989287`

**In plain English:** A provider is a company or a server that runs language models. RagAssist talks to each provider
through one small adapter class. This page lists every place that you touch to add one. It uses Gemini as the worked
example, because [ADR 0013](../adr/0013-gemini-provider.md) added it last.

## Goal

Add a provider so that a model of that provider can serve any role (generator, rewriter, agent, judge, decider), and so
that a missing key does not break the system.

## Before you start

- You know the terms [fallback chain](../glossary.md), [models.yaml](../glossary.md) and role. Read the
  [models catalog](../reference/models-catalog.md) first.
- Before you code, write the goal in one or two sentences. Read the official documentation of the provider: the base URL,
  the authentication header, tool calling, structured output and streaming. Prefer a library that the project already uses
  (`langchain-openai` serves every OpenAI-compatible endpoint) to a new SDK. Record the pages that you read in the adapter
  docstring. Never guess an SDK signature. See `AGENTS.md`, section 3.5.
- Keys and endpoints come from settings and `.env`. They are never in code.

> **WARNING.** Do not put a key in `config/models.yaml`, in a test or in a document. The provider key belongs in `.env`.
> Mask it in the settings, as step 4 shows.

## Steps

1. Make the adapter file `src/ragassist/platform/llm/adapters/<name>_adapter.py`. The Gemini file is
   `gemini_adapter.py`. The class extends `ChatModelProvider` from `src/ragassist/platform/llm/ports.py` and has these
   members:

   | Member | Job |
   |---|---|
   | `name` (property) | The provider name, for example `gemini` |
   | `get_capabilities(model_name)` | Tools, JSON schema, streaming, logprobs, vision, context window and pricing |
   | `get_pricing(model_name)` | The price, read from the catalog |
   | `build_chat_model(model_name, temperature, max_tokens, streaming, **extra)` | Returns a LangChain chat model |
   | `get_chat_model(model, ...)` | Calls `build_chat_model` |

2. Build the chat model from the settings. The Gemini adapter returns `ChatOpenAI` with `base_url` from
   `GEMINI_BASE_URL` and `api_key` from `GEMINI_API_KEY`. When the key is empty, it sends the placeholder
   `UNCONFIGURED_KEY` (the text `unconfigured`). The request then fails and the chain moves on.
3. Export the class in `src/ragassist/platform/llm/adapters/__init__.py`.
4. Add the settings in `src/ragassist/shared/config/settings.py`:

   - the key field, with the default empty string (`GEMINI_API_KEY: str = ""`)
   - the base URL field, **required** with no default (`GEMINI_BASE_URL: str`)
   - the key name in both masked lists: `__repr__` and `model_dump_json`

5. Update `.env.example` in the same change. Leave the key blank. Write a non-secret value for the base URL. Add a
   comment that says the key is optional. The test `tests/hygiene/test_env_example.py` checks this.
6. Register the adapter in `create_default_llm_registry` in `src/ragassist/platform/llm/service.py`:

   ```python
   registry.register("gemini", lambda: GeminiAdapter(settings=active_settings))
   ```

7. Describe the provider in `config/models.yaml`, under `providers`:

   ```yaml
   gemini:
     adapter: gemini
     api_key_env: GEMINI_API_KEY
     base_url_env: GEMINI_BASE_URL
     timeout_seconds: 60.0
     skip_when_unconfigured: true
   ```

   With `skip_when_unconfigured: true`, the provider is dropped from a fallback list when its key is empty.

8. Add the models under `models`. Give each one `provider`, `model_name`, `context_window`, `max_output_tokens`,
   `pricing`, `capabilities` and `default_params`. The `ModelDefinitionConfig` class forbids extra fields, so a
   misspelled field fails at load time. Copy limits and prices from the official model pages and write the source in a
   comment. Mark anything that you could not check as `UNVERIFIED`.

   > **CAUTION.** Do not repeat a key in one model entry. YAML loaders usually keep the last value and do not warn. The
   > entry `claude-haiku-5-5` has a repeated `pricing:` key at this commit. Check that your entry has each key once.

9. Add aliases under `aliases`, for example `gemini-flash: "gemini-flash-latest"`.
10. Add the provider to the `fallbacks` of the roles where you want it, in the `roles` section.
11. Add a row for the provider to the table in `README.md` and to the [models catalog](../reference/models-catalog.md).
12. Write or update an ADR in `docs/adr/`. An example is `docs/adr/0013-gemini-provider.md`.
13. Write the tests. Use the `ChatModelProviderContract` in `tests/support/contracts/chat_provider.py` and the
    `make_settings` helper. The Gemini example is `tests/unit/platform/llm/test_gemini_provider.py`. Test that an empty
    key gives the placeholder and that the provider is skipped as a fallback without a key.
14. Rebuild and recreate the containers that read the code and `config/`:

    ```bash
    docker compose up -d --build api worker
    ```

    The image copies `src/` and `config/` at build time. There is no bind mount.

## Check

- `pytest tests/unit/platform/llm tests/hygiene` passes. See [run the tests](run-the-tests.md).
- With the key set, a role that names the new model answers a question.
- With the key empty, the provider is absent from the fallbacks and the other models still answer.
- `lint-imports` exits with 0.

## Troubleshooting

- The system stops at start-up with a validation error. A model entry has a field that the schema does not know, or the
  base URL setting has no value.
- The new provider is never tried. It is not in a `fallbacks` list, or its key is empty and
  `skip_when_unconfigured` is true.
- Calls fail with 404. The model id is retired or misspelled. Check the provider documentation.
- More help: [configure LLM providers and fallbacks](configure-llm-providers-and-fallbacks.md) and
  [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Ports and adapters](../reference/ports-and-adapters.md)
- [Configuration reference, section 9](../reference/configuration.md#9-model-providers)
- [ADR 0004: decision layer](../adr/0004-decision-layer.md)
