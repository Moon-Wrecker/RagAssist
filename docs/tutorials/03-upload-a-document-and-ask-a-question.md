# Upload a document and ask a question

**Type:** Tutorial · **Audience:** a developer who finished lesson 2 · **Verified against:** `a989287`

**In plain English:** In this lesson you add one small file to the [knowledge base](../glossary.md). You wait until the
system has read it. Then you ask a question and the assistant answers from your file and shows its source. At the end
you have seen the main feature of RagAssist: an answer that points to a document.

The lesson before this one is [create a workspace and sign in](02-create-a-workspace-and-sign-in.md).

## What you will build

You will make a short returns policy for the invented company Acme. You will upload it. You will ask how long a
customer has to ask for a refund.

## Before you start

- You are signed in as `ada@example.test` in the workspace `demo`.
- The `worker` part runs. `docker compose ps` shows `worker` as `running`.
- `OPENAI_API_KEY` has your own value in `.env`. The default embeddings need it.

## Steps

1. On your computer, make a text file with the name `acme-returns-policy.md`.
2. Put this text in the file and save it:

   ```markdown
   # Acme returns policy

   ## Refund window
   A customer can ask for a refund within 30 days of the purchase date.
   After 30 days Acme gives store credit only.

   ## How to return an item
   Pack the item in the original box. Print the return label from the order page.
   Acme pays for the label when the item is faulty.
   ```

   The numbers in this file are invented for the lesson.

3. In the web app, select Knowledge in the navigation.
4. Select the button "Choose files".
5. Pick `acme-returns-policy.md`. The page accepts PDF, Markdown, HTML and CSV files up to 50 MiB.
6. Watch the row of the file. Its state is Queued, then Indexing, then Ready.

   While the state is Indexing, the row shows the stage. The stages are "Reading the file", "Splitting into passages",
   "Computing embeddings" and "Saving to the index". A small file takes a few seconds.

7. Wait until the state is Ready.
8. Select Chat in the navigation.
9. Click the input field "Ask about your account or the documents".
10. Type `How long do I have to ask for a refund?` and send the message.
11. Watch the answer. The page first shows "Looking through your documents". Then the answer text arrives in small parts.
12. Look under the answer for the label "Sources". A chip shows the name of your file.
13. Select the chip. The citation panel opens and shows the passage that the assistant used.

## Check

- The answer says 30 days.
- The source chip names `acme-returns-policy.md`.
- The citation panel shows the text about the refund window.

## If something is wrong

- The state is Failed. Open the row menu "Actions for acme-returns-policy.md" and select Re-index. If it fails again,
  read the logs: `docker compose logs worker`. See
  [manage the knowledge base](../how-to/manage-the-knowledge-base.md).
- The state stays Queued. The worker is not running or cannot reach the queue. Run `docker compose ps` and
  `docker compose logs worker`.
- The answer says that the assistant cannot run a check. The system could not reach a model. Check the provider key in
  `.env`. See [configure LLM providers and fallbacks](../how-to/configure-llm-providers-and-fallbacks.md).
- The answer has no source chip. The system did not find a passage that matches. Ask a question with words from the
  file.
- The upload page refuses the file. The file type or the size is not allowed. The API answers 415 for a type that it
  does not accept.

## What happened behind the scenes

The browser sent the file to the API. The API stored it and queued a job. The worker read the file, split it into
passages, made an embedding for each passage and saved them in `postgres`. When you asked, the
[assistant graph](../reference/assistant-graph.md) checked the question for safety, found the best passages and
asked a model to answer from them. The live answer reached the browser as a stream of events. The contract for that
stream is in [the SSE contract](../api/sse-contract.md).

Unverified: the author did not run these steps against a live stack. The wording of the answer depends on the model.

## Next step

Go on to [handle an escalation as an agent](04-handle-an-escalation-as-an-agent.md).
