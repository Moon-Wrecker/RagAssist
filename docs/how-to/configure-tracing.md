# Configure tracing

**Type:** How-to · **Audience:** an operator who wants to see what the assistant does · **Verified against:** `a989287`

**In plain English:** This page shows how to turn on Langfuse tracing or LangSmith tracing, how to confirm that it
works and how to turn it off. Tracing records each turn of the assistant. It also sends private text to another
service, so read the warning first.

## Goal

Send the traces of the assistant to [Langfuse](../glossary.md) (the default choice), or to LangSmith.

## Before you start

- A Langfuse project with a public key and a secret key. You can use Langfuse Cloud or your own server.
- You read [observability](../reference/observability.md) and [ADR 0012](../adr/0012-langfuse-tracing.md).
- To learn by doing first, follow [follow a turn in Langfuse](../tutorials/05-follow-a-turn-in-langfuse.md).

> **WARNING.** Traces include the text of the conversation and the passages that the search found. The code replaces
> credentials with `[REDACTED]`. It does not remove other private text. Send traces only to a service that you control
> and that your data rules allow.

## Steps for Langfuse

1. Open `.env`.
2. Set `LANGFUSE_TRACING=true`.
3. Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to the values of your project.
4. Set `LANGFUSE_BASE_URL` to your server. The template value is Langfuse Cloud.
5. Leave `LANGFUSE_SAMPLE_RATE` at 1.0 to keep every trace. Use a smaller number to keep a part.
6. Save the file.
7. Recreate the API:

   ```bash
   docker compose up -d --force-recreate api
   ```

8. Ask one question in the chat.
9. Run `docker compose logs api` and look for the line `tracing.enabled`.

The client starts lazily at the first traced turn. The `tracing.enabled` line therefore appears after the first
question, not at start-up. The line shows `base_url` and `environment`. The environment is the value of `APP_ENV`.

## Steps for LangSmith (optional)

1. Set `LANGSMITH_TRACING=true` in `.env`.
2. Set `LANGSMITH_API_KEY` to your own key.
3. Set `LANGSMITH_PROJECT` and, for a private server, `LANGSMITH_ENDPOINT`.
4. Recreate the API as in step 7 above.

## Check

- The log shows `tracing.enabled`.
- Langfuse shows a trace named `answer-question` (or `decide-action` for an approval) with the child observations
  `check-safety`, `route-question` and `retrieve-passages`.
- The session of the trace is the id of the conversation.

## Turn tracing off

1. Set `LANGFUSE_TRACING=false` in `.env`.
2. Recreate the API.

## Troubleshooting

- The log shows `tracing.disabled`. A key is missing. Set both keys.
- No trace appears in Langfuse. Check the base URL, wait a minute, and check `LANGFUSE_SAMPLE_RATE`.
- The trace shows `[REDACTED]` in a field. This is the redaction at work.
- You plan to read traces by API. The Langfuse v1 read endpoints are removed on 2026-11-16. Use
  `GET /api/public/v2/observations`.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Configuration reference, section 16](../reference/configuration.md#16-observability)
- [Observability reference](../reference/observability.md)
