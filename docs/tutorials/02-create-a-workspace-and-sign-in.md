# Create a workspace and sign in

**Type:** Tutorial · **Audience:** a developer who finished lesson 1 · **Verified against:** `a989287`

**In plain English:** In this lesson you make a new [workspace](../glossary.md) called Acme. You get a one-time link, set
a password and sign in as the first administrator. At the end you see the chat page. A workspace is one customer
company. Its data stays apart from the data of all other workspaces.

The lesson before this one is [run the stack locally](01-run-the-stack-locally.md). Do that first.

## What you will build

You will make these items:

| Item | Value in this lesson |
|---|---|
| Workspace name | Acme Inc |
| Workspace slug | `demo` |
| First administrator | `ada@example.test` |

The slug is the short name that you type on the sign-in page. It uses lower-case letters, digits and hyphens. It must
match `^[a-z0-9][a-z0-9-]{1,62}$`.

## Before you start

- The stack from lesson 1 runs. `docker compose ps` shows `api` and `web` as `healthy`.
- You know your `<WEB_PORT>` value from `.env`.

## Steps

1. Open a terminal in the root folder of the repository.
2. Create the workspace inside the `api` container:

   ```bash
   docker compose exec api ragassist workspace create --name "Acme Inc" --slug demo --admin-email ada@example.test
   ```

   The container already has the database settings. You do not need to pass them.

3. Read the output. The first line is `Workspace 'demo' created (<id>).` The `<id>` is a number that the system made.
4. Find the line that says the link is shown once and works once. The next line is the link. It looks like
   `http://localhost:<WEB_PORT>/accept#token=...`.

   > **WARNING.** The link lets a person set the password of the administrator. Treat it like a password. Do not post
   > it in a chat, a ticket or a document. The system shows it one time. It stops working after one use. It also stops
   > after `AUTH_INVITE_HOURS` hours (72 in `.env.example`).

5. Copy the whole link into your browser. The page title is "Set your password".
6. Type a password in the field "New password". The password must have at least 12 characters and at most 128. It must
   not be the same as the email address.
7. Type the same password in the field "Repeat the password".
8. Select "Set password and sign in". The browser opens the chat page.
9. Look at the top of the page. The navigation shows Chat, Inbox, Knowledge and Team. An administrator sees all four.

The part of the link after `#` is a fragment. The browser does not send a fragment to the server in a normal request.
The page reads it and sends it to the API in the body of one request.

## Check

- You see the chat page with the input field "Ask about your account or the documents".
- Sign out and sign in again to prove that the password works. On the sign-in page enter Workspace `demo`, Email
  `ada@example.test` and your password. Select "Sign in".

## If something is wrong

- The command exits with code 1 and prints a message. A domain error means the slug is in use or the slug is not valid.
  Pick a different slug.
- The command exits with code 2. A required option is missing. Add `--name`, `--slug` and `--admin-email`.
- The link says it is not valid. It was used once, or it expired. Make a new link from the Team page (lesson 4) or
  create a workspace with another slug.
- The app asks you to sign in again after a page reload, or the API answers "Cross-origin request refused." to a
  refresh request. The value `WEB_BASE_URL` in `.env` does not match the address in your browser. Fix it and run
  `docker compose up -d --force-recreate api`. See
  [troubleshoot common problems](../how-to/troubleshoot-common-problems.md).
- The command fails because it cannot reach the database. Unverified: the author did not run
  `docker compose exec api ragassist workspace create` on a live stack. The container should inherit `DB_HOST` from
  compose.

## What happened behind the scenes

The command created a row for the workspace and a row for the administrator. It then made an invite link for the
administrator. See [the command-line reference](../reference/cli.md) for every option, and
[roles and permissions](../reference/roles-and-permissions.md) for what an administrator can do.

## Next step

Go on to [upload a document and ask a question](03-upload-a-document-and-ask-a-question.md).
