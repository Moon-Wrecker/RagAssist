# Follow a turn in Langfuse

**Type:** Tutorial · **Audience:** a developer who finished lesson 3 · **Verified against:** `a989287`

**In plain English:** In this lesson you connect RagAssist to [Langfuse](../glossary.md), a tool that records what the
assistant does. You ask one question. Then you open the recorded trace and read the steps. At the end you can see
which safety check, route and search passages the assistant used for one answer.

Do lesson 3, [upload a document and ask a question](03-upload-a-document-and-ask-a-question.md), first. Lesson 4 is not required.

## What you will build

You will turn tracing on. You will find the trace of one question and read its observations.

## Before you start

- A Langfuse project. You can use Langfuse Cloud or your own Langfuse server.
- The public key and the secret key of that project. Keep them private.
- The stack runs and you signed in at least once.

> **WARNING.** Tracing sends the text of conversations and the retrieved passages to Langfuse. The code replaces
> credentials with `[REDACTED]`, but it does not remove other private text. Use a project that you control. Do not
> turn tracing on for real customer data without a decision from your data owner.

## Steps

1. Open `.env` in your editor.
2. Find `LANGFUSE_TRACING`. Set it to `true`.
3. Find `LANGFUSE_PUBLIC_KEY`. Paste the public key of your project.
4. Find `LANGFUSE_SECRET_KEY`. Paste the secret key of your project.
5. Find `LANGFUSE_BASE_URL`. Keep the template value for Langfuse Cloud, or enter the address of your own server.
6. Save the file.

   > **CAUTION.** Compose reads `.env` only when it creates a container. A plain `docker compose up -d` may keep the old
   > container. Use the option that forces a new one.

7. Recreate the API:

   ```bash
   docker compose up -d --force-recreate api
   ```

8. Sign in to the web app and ask any question in Chat.
9. Check the log of the API:

   ```bash
   docker compose logs api
   ```

10. Find the line `tracing.enabled`. It shows the `base_url` and the `environment`. The client starts at the first
    traced turn, so the line appears after your question.
11. Open your Langfuse project in the browser.
12. Open the list of traces. Unverified: the menu names in the Langfuse web page can change. Look for the traces list.
13. Open the newest trace. Its name is `answer-question`.
14. Look at the child observations. You see `check-safety`, `route-question` and `retrieve-passages`.
15. Open `retrieve-passages`. Read the passages that the search found for your question.
16. Look at the session field. It holds the id of your conversation. Ask a second question in the same chat. The new
    trace has the same session.

## Check

- The log shows `tracing.enabled`.
- A trace named `answer-question` exists for your question.
- The trace shows the three child observations.

For an action that needs approval, the root observation is named `decide-action` and not `answer-question`.

## If something is wrong

- The log shows the warning `tracing.disabled`. One of the keys is missing. Fix `.env` and recreate the API.
- No trace appears. Wait a minute. The client sends in batches. Check that `LANGFUSE_SAMPLE_RATE` is 1.0 (the template
  value). A smaller value keeps only a part of the traces.
- You use a Langfuse server that is old. Unverified: the author did not test other server versions. See
  [configure tracing](../how-to/configure-tracing.md).

## What happened behind the scenes

The trace has the tags `assistant` and the mode of the turn. The metadata holds `tenant_id` and `role`. The user field
holds the user id. See [observability](../reference/observability.md) and [ADR 0012](../adr/0012-langfuse-tracing.md).

Unverified: the author did not run these steps against a live Langfuse project.

## End of the tutorials

You ran the stack, made a workspace, used the knowledge base, handled an escalation and read a trace. For the next
steps, read the how-to pages, for example [configure LLM providers and fallbacks](../how-to/configure-llm-providers-and-fallbacks.md).
