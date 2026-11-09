import { PlaceholderPage } from "./placeholder-page";

export function ChatPage() {
  return (
    <PlaceholderPage title="Chat">
      Conversations with the assistant arrive in the next release. There is nothing to do here yet.
    </PlaceholderPage>
  );
}

export function InboxPage() {
  return (
    <PlaceholderPage title="Inbox">
      Escalated conversations will land here for agents to answer. Nothing is waiting for you yet.
    </PlaceholderPage>
  );
}

export function KnowledgePage() {
  return (
    <PlaceholderPage title="Knowledge">
      Uploading and managing the documents the assistant answers from arrives in a later release.
    </PlaceholderPage>
  );
}

export function TeamPage() {
  return (
    <PlaceholderPage title="Team">
      Inviting people and managing roles arrives in a later release. Until then, an administrator uses the command
      line to create workspaces and links.
    </PlaceholderPage>
  );
}
