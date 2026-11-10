# Manage the team and invites

**Type:** How-to · **Audience:** a workspace administrator · **Verified against:** `a989287`

**In plain English:** This page shows how an administrator adds people to the [workspace](../glossary.md), resets a
password, stops a person from signing in and revokes a link that nobody used. All steps happen on the Team page.

## Goal

Add a person with the right role, and keep the member list correct over time.

## Before you start

- You are signed in with the role `admin`. Other roles do not see the Team page.
- You know the three roles: Customer (`user`), Support agent (`agent`) and Admin (`admin`). See
  [roles and permissions](../reference/roles-and-permissions.md).
- You know that a link is an [invite](../glossary.md). It works once and it expires after `AUTH_INVITE_HOURS` hours (72 in
  `.env.example`).

## Invite a person

1. Select Team in the navigation.
2. Select "Invite". The dialog "Invite someone" opens.
3. Type the email address in "Email address".
4. Choose the role in the Role list: Customer, Support agent or Admin.
5. Select "Create invite link". The dialog shows "Invite link ready".
6. Select "Copy link".

   > **WARNING.** The link lets the holder set a password for that account. Send it only to the person, in a private
   > channel. Do not paste it in a public chat or a ticket.

7. Send the link to the person.
8. Select "Done".

The person opens the link, enters a password of 12 to 128 characters and is signed in. The password must not be the same
as the email address.

## Reset the password of a member

1. Find the person in the member list.
2. Open the row menu.
3. Select "Reset password link". The dialog shows a new link.
4. Copy the link and send it as in the steps above.

## Stop a person from signing in

1. Open the row menu of the person.
2. Select "Deactivate".
3. In the dialog, select "Deactivate" again.

The member list now shows the state Deactivated. To undo it, open the row menu and select "Reactivate".

The states in the list are Active, Deactivated and "Not signed in yet". The last state means that the person has not used
the link.

## Revoke a link that nobody used

1. Look at the section "Pending links".
2. Find the link.
3. Select the revoke control of that row.

## Check

- The new person appears in the member list with the right role.
- After the person uses the link, the state changes from "Not signed in yet" to Active.
- A deactivated person cannot sign in.

## Troubleshooting

- The person says that the link is not valid. It was used, revoked or expired. Create a new link with "Reset password
  link".
- The person signs in but a reload signs them out, or the refresh request answers "Cross-origin request refused." `WEB_BASE_URL` in `.env` does not match the address of the browser.
  See [troubleshoot common problems](troubleshoot-common-problems.md).
- You cannot see the Team page. Your role is not `admin`.
- To create the first administrator of a new workspace, use `ragassist workspace create`. See
  [the command-line reference](../reference/cli.md).

## Related pages

- [Accounts, sessions and tokens](../explanation/accounts-sessions-and-tokens.md)
- [ADR 0007: accounts and sessions](../adr/0007-accounts-and-sessions.md)
- [API endpoints for the team](../reference/api-endpoints.md)
