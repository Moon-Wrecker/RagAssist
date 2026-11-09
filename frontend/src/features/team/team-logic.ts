import type { Invite, Member, MemberPatch } from "@/api/team";
import type { Role } from "@/api/types";

/** Pure member and invite logic for the team screen. No React, no network. */

export const ROLE_LABELS: Record<Role, string> = {
  user: "Customer",
  agent: "Support agent",
  admin: "Admin",
};

export const ROLE_ORDER: readonly Role[] = ["user", "agent", "admin"];

export const ROLE_HINTS: Record<Role, string> = {
  user: "Chats with the assistant.",
  agent: "Also answers escalated conversations in the inbox.",
  admin: "Also manages knowledge and the team.",
};

export type MemberState = "active" | "deactivated" | "awaiting";

/** Deactivated wins; an active account that never set a password is still waiting for its first sign-in. */
export function memberState(member: Pick<Member, "status" | "has_password">): MemberState {
  if (member.status === "disabled") return "deactivated";
  return member.has_password ? "active" : "awaiting";
}

export const STATE_LABELS: Record<MemberState, string> = {
  active: "Active",
  deactivated: "Deactivated",
  awaiting: "Not signed in yet",
};

/** The list with one member's role or status changed. Unknown ids change nothing; the input is not mutated. */
export function applyMemberPatch(members: readonly Member[], id: string, patch: MemberPatch): Member[] {
  return members.map((member) =>
    member.id === id
      ? { ...member, ...(patch.role ? { role: patch.role } : {}), ...(patch.status ? { status: patch.status } : {}) }
      : member,
  );
}

export function withoutInvite(invites: readonly Invite[], id: string): Invite[] {
  return invites.filter((invite) => invite.id !== id);
}

export function inviteKindLabel(kind: string): string {
  return kind === "reset" ? "Password reset" : "Invitation";
}

/** True when nothing about the change is a change (the select was set to the value it already had). */
export function isNoop(member: Pick<Member, "role" | "status">, patch: MemberPatch): boolean {
  return (!patch.role || patch.role === member.role) && (!patch.status || patch.status === member.status);
}
