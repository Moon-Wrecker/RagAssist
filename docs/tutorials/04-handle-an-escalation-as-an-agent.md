# Handle an escalation as an agent

**Type:** Tutorial · **Audience:** a developer who finished lesson 3 · **Verified against:** `a989287`

**In plain English:** In this lesson you play three people. A customer asks for a human. A support agent answers in the
inbox. The administrator makes both accounts. At the end you see an [escalation](../glossary.md) from both sides: the
customer sees the reply live and the agent hands the chat back to the assistant.

The lesson before this one is [upload a document and ask a question](03-upload-a-document-and-ask-a-question.md).

## What you will build

| Person | Role | Email |
|---|---|---|
| Ada | admin | `ada@example.test` (from lesson 2) |
| Grace | support agent | `grace@example.test` |
| Linus | customer (role `user`) | `linus@example.test` |

You need two browser sessions at the same time. Use one normal window and one private window. Each keeps its own
session.

## Before you start

- You are signed in as Ada in the normal window.
- The stack runs and a model key is set in `.env`.

## Steps: make the two accounts

1. In the normal window, select Team in the navigation.
2. Select the button "Invite". The dialog "Invite someone" opens.
3. Type `grace@example.test` in "Email address".
4. In the Role list, select "Support agent".
5. Select "Create invite link". The dialog shows "Invite link ready".
6. Select "Copy link".

   > **WARNING.** The link sets the password of Grace. Do not share it outside this lesson.

7. Paste the link into the **private** window. The page "Set your password" opens.
8. Set a password of 12 or more characters in both fields. Select "Set password and sign in".
9. The private window now shows Grace. Sign out of it. The menu has the sign-out command.
10. Go back to the normal window. In the dialog select "Done".
11. Repeat steps 2 to 6 for `linus@example.test`. Select the role "Customer".
12. Open the link in the private window, set a password and stay signed in as Linus.

## Steps: ask for a human

1. In the private window, signed in as Linus, select Chat.
2. Type `I want to speak to a human` and send the message.
3. Read the page. The conversation shows the line "A support agent has taken over" and a ticket label ("Ticket" and
   an id).
4. Look at the input field. Its placeholder is now "Write to the support agent".

The assistant stops answering this conversation until an agent hands it back.

## Steps: answer as the agent

1. In the normal window, sign out of Ada.
2. Sign in as Grace. Use Workspace `demo`, Email `grace@example.test` and the password that you set.
3. Select Inbox in the navigation. The filter "Needs a reply" is active. The list shows the escalation of Linus.
4. Look at the status indicator. It shows "Live". If it shows "Reconnecting", wait ten seconds.
5. Select the escalation. The page shows the conversation.
6. Type a short answer in the field "Write to the customer".
7. Select "Send reply".
8. Look at the private window. Linus sees the answer live. The message shows the name "Support agent".
9. In the normal window, select "Resolve and hand back".
10. In the private window, write another question as Linus. The assistant answers again.

## Check

- The reply of Grace appeared in the window of Linus without a page reload.
- The escalation moved from "Needs a reply" to Resolved in the inbox of Grace.
- The assistant answered the new question of Linus.

## If something is wrong

- The assistant answered instead of escalating. The phrase did not match. The rules decider knows these phrases: "speak
  to a human", "real human", "transfer me", "human representative", "file a complaint", "get me a supervisor", "speak to
  agent", "talk to representative" and "human support". Unverified: the author confirmed only the rules decider. Another
  decider in the chain may route a phrase in another way.
- Ada gets an error when she replies. Only the `agent` role can reply. An administrator gets 403. Sign in as Grace. See
  [roles and permissions](../reference/roles-and-permissions.md).
- The inbox shows "Reconnecting" for a long time. See
  [troubleshoot common problems](../how-to/troubleshoot-common-problems.md).
- The invite link says it is not valid. A link works once. Make a new one with "Reset password link" in the row menu of
  the person on the Team page. See [manage the team and invites](../how-to/manage-team-and-invites.md).

## What happened behind the scenes

The assistant graph routed the message to the human-escalation node. The node made a ticket, told the browser through a
live event and stopped. The reply of Grace went to `POST /v1/escalations/{id}/reply`. Resolving called
`/resolve` and gave the conversation back to the assistant. The design is in
[ADR 0008](../adr/0008-live-events-handoff-and-detached-turns.md).

Unverified: the author did not run these steps against a live stack.

## Next step

Go on to [follow a turn in Langfuse](05-follow-a-turn-in-langfuse.md).
