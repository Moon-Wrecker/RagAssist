# ADR 0010: Google Gemini as a First-Class Chat Provider

## Context & Problem
Gemini models were reachable only by pointing `OPENAI_COMPATIBLE_*` at Google's endpoint, and `OPENAI_COMPATIBLE_MODEL`
then sends **every** role to that one model. That setup collides with a local Ollama configuration (one endpoint, one
key) and gives no catalog entries, pricing or per-role choice. We want Gemini selectable per role, next to OpenAI,
Anthropic, OpenRouter and a local server, without disturbing any of them.

## Decision
1. **A dedicated `gemini` provider** with its own settings: `GEMINI_API_KEY` (optional, empty default, masked in
   `repr` and JSON like every other key) and `GEMINI_BASE_URL` (required, non-secret; `.env.example` carries
   `https://generativelanguage.googleapis.com/v1beta/openai/`). `OPENAI_COMPATIBLE_*` is untouched, so Ollama keeps
   working, and Gemini never receives another provider's key (tested).
2. **No new SDK.** Google documents an OpenAI-compatible endpoint (Bearer auth, function calling, structured output,
   streaming), so `GeminiAdapter` builds a `langchain_openai.ChatOpenAI` against `GEMINI_BASE_URL`, exactly as the
   OpenRouter and compatible adapters do. `langchain-google-genai` was not adopted: it would add a dependency and a
   second tool-calling code path for no capability we use.
3. **Catalog (`config/models.yaml`)**: `gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-pro-latest` (moving
   aliases) and the pinned stable `gemini-3.8-flash` and `gemini-3.5-flash-lite`, with aliases `gemini-flash`,
   `gemini-flash-lite`, `gemini-pro`, `gen-gemini`.
4. **Fallbacks only, never default primaries.** Gemini is appended as the LAST fallback of every role (`generator` and
   `agent`: `gemini-flash-latest`; `rewriter`, `judge`, `decider`: `gemini-flash-lite-latest`). Primaries are
   unchanged. Choosing Gemini as a primary stays an explicit choice (`LLM_ROLE_*_PRIMARY=gemini-flash`).
5. **Unconfigured providers are skipped, not tried.** A provider can declare `skip_when_unconfigured: true`; if the
   key named by its `api_key_env` is empty, `ModelCatalog.resolve_role_chain` leaves its models out of a role's
   *fallbacks* (the primary position is never filtered). Only `gemini` sets the flag, so with `GEMINI_API_KEY` empty
   every role chain is identical to the pre-change chain (tested), and no request pays a guaranteed 401 round trip.
   Other providers keep their existing behaviour.
6. **Embeddings are not added.** The pgvector column is `Vector(1536)` and `EMBEDDING_DIMENSION=1536`; Google's
   embedding models (`gemini-embedding-001`, `gemini-embedding-2`) do not document a 1536 dimension on the pages we
   consulted, and the existing embedding adapters read `OPENAI_COMPATIBLE_*`, so this is not trivial. Changing the
   schema is out of scope. Revisit with a verified `dimensions` truncation to 1536.

## Verified facts (2026-11-10) and sources
- https://ai.google.dev/gemini-api/docs/openai (redirects to aistudio.google.com/docs/openai): base URL, Bearer auth,
  function calling, structured output, streaming, `reasoning_effort`; support "still in beta".
- https://ai.google.dev/gemini-api/docs/models and the per-model pages (`.../models/gemini-3.8-flash`,
  `gemini-3.5-flash-lite`, `gemini-3.1-pro-preview`, `gemini-3.6-flash`): every one lists input limit 1,048,576, output
  limit 65,536, function calling, structured outputs, thinking, caching and image input as supported.
  `gemini-3.8-flash` and `gemini-3.5-flash-lite` are Stable; `gemini-3.1-pro-preview` is a preview.
- https://ai.google.dev/gemini-api/docs/pricing (Standard tier, USD per 1M tokens, output includes thinking):
  `gemini-3.8-flash` 0.75 in / 3.75 out; `gemini-3.5-flash-lite` 0.30 / 2.50; `gemini-3.1-pro-preview` 2.00 / 12.00 up
  to 200k prompt tokens (4.00 / 18.00 above; the catalog stores the lower tier). **Scheduled change:** `gemini-3.8-flash`
  becomes 1.50 / 7.50 on 2027-01-01, so the catalog price must be revisited then.
- The "Latest" section of the models page: an alias "will get hot-swapped with every new release of a specific model
  variation", with "a 2-week notice ... through email"; it advises that most production apps use a specific stable
  model. Hence the pinned entries.
- Live checks with a real key (not committed): `gemini-flash-latest` and `gemini-flash-lite-latest` answered HTTP 200 on
  `chat/completions`; `gemini-pro-latest` answered HTTP 429 (the account's free tier has quota 0 for it) and the error
  names `gemini-3.1-pro`.

## Unverified
- Which concrete model `gemini-flash-latest` and `gemini-flash-lite-latest` resolve to today: the docs do not say and the
  API echoes the alias. The catalog copies limits and prices from `gemini-3.8-flash` and `gemini-3.5-flash-lite`, the
  newest stable Flash and Flash-Lite in the docs; they may differ if an alias points elsewhere.
- Only `gemini-flash-latest` is named in the docs; `gemini-flash-lite-latest` and `gemini-pro-latest` work against the
  endpoint but are undocumented there.
- `logprobs` support (not documented, set false) and a recommended temperature (the Gemini 3 page does not state one;
  the catalog keeps the repository's low defaults).

## Consequences
- **Positive:** Gemini is usable per role or as a safety net, beside a local Ollama setup; zero behaviour change and zero
  extra calls without a key; one more place to rotate nothing (the key lives only in `.env`).
- **Negative:** `GEMINI_BASE_URL` is a new required setting, so an existing `.env` must gain the line from
  `.env.example` (or be regenerated with `ragassist init-env`). Alias targets can change under us; prices need a manual
  refresh. Gemini's OpenAI compatibility layer is in beta.
