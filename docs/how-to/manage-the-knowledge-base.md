# Manage the knowledge base

**Type:** How-to · **Audience:** a workspace administrator · **Verified against:** `a989287`

**In plain English:** This page shows how an administrator adds files to the [knowledge base](../glossary.md), checks
that the system read them, indexes a file again and deletes a file. The assistant answers from these files.

## Goal

Keep the files of the workspace current, so that answers use the right text.

## Before you start

- You are signed in with the role `admin`.
- The `worker` container runs. It reads the files.
- The embedding provider has a key. The template sets `EMBEDDING_PROVIDER=openai`. That value needs `OPENAI_API_KEY` in `.env`.
- Your file is a PDF, Markdown, HTML or CSV file. The size is 50 MiB or less.

## Add files

1. Select Knowledge in the navigation.
2. Select "Choose files".
3. Pick one or more files.
4. Watch the state of each row: Queued, Indexing, then Ready.
5. While a row shows Indexing, read its stage: "Reading the file", "Splitting into passages", "Computing embeddings" or
   "Saving to the index".

## Index a file again

Do this after a failure or after you change the embedding settings.

1. Open the row menu "Actions for <file>".
2. Select Re-index.
3. Wait until the state is Ready.

## Delete a file

> **WARNING.** Delete removes the document and its passages. The assistant can no longer answer from the file. The
> action cannot be undone from the page. Keep a copy of the original file.

1. Open the row menu "Actions for <file>".
2. Select Delete.
3. Read the dialog. Select "Delete document" to confirm. Select "Keep it" to cancel.

## Check

- The state is Ready.
- Ask a question about the file in Chat. The answer shows a source chip with the file name.
- After a delete, the file is gone from the list and the assistant stops using it.

## Limits to know

- The API accepts a file of up to 50 MiB. The web proxy allows 52 MiB on `/v1/documents` so that the API gives the error.
- The API answers 415 for a file type that it does not allow. The allowed types are Markdown, HTML, CSV and PDF. The
  README names other types (JSON and TXT). The code does not accept them at this commit.
- The search embeddings have a fixed size of 1536 dimensions in the shipped schema. See
  [configuration](../reference/configuration.md#11-embeddings-and-vector-search).
- The container image does not include the optional `ml` extra. Local models for embeddings and the cross-encoder are
  not in the container. This is an open limit.

## Troubleshooting

- The state is Failed. Run `docker compose logs worker`, fix the cause, then select Re-index.
- The state stays Queued. The worker is stopped. Run `docker compose ps` and start it with
  `docker compose up -d worker`.
- The upload is refused with 413. The file is too large.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Ingestion components](../c4/05-components-ingestion.md)
- [Data model](../reference/data-model.md)
- [Follow-along lesson](../tutorials/03-upload-a-document-and-ask-a-question.md)
