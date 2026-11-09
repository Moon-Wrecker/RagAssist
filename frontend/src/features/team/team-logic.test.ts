import { describe, expect, it } from "vitest";
import type { Invite, Member } from "@/api/team";
import { applyMemberPatch, inviteKindLabel, isNoop, memberState, withoutInvite } from "./team-logic";

const members: Member[] = [
  { id: "1", email: "a@example.test", role: "admin", status: "active", has_password: true },
  { id: "2", email: "b@example.test", role: "user", status: "active", has_password: true },
  { id: "3", email: "c@example.test", role: "agent", status: "disabled", has_password: true },
  { id: "4", email: "d@example.test", role: "user", status: "active", has_password: false },
];

describe("memberState", () => {
  it("tells active, deactivated and not-yet-signed-in apart", () => {
    expect(memberState(members[1]!)).toBe("active");
    expect(memberState(members[2]!)).toBe("deactivated");
    expect(memberState(members[3]!)).toBe("awaiting");
  });

  it("treats a deactivated account as deactivated even without a password", () => {
    expect(memberState({ status: "disabled", has_password: false })).toBe("deactivated");
  });
});

describe("applyMemberPatch", () => {
  it("changes a role and leaves everyone else alone", () => {
    const next = applyMemberPatch(members, "2", { role: "agent" });
    expect(next[1]).toMatchObject({ id: "2", role: "agent", status: "active" });
    expect(next[0]).toEqual(members[0]);
    expect(members[1]?.role).toBe("user");
  });

  it("changes a status, and both at once", () => {
    expect(applyMemberPatch(members, "2", { status: "disabled" })[1]?.status).toBe("disabled");
    expect(applyMemberPatch(members, "3", { role: "user", status: "active" })[2]).toMatchObject({ role: "user", status: "active" });
  });

  it("ignores null fields, and an id that is not in the list", () => {
    expect(applyMemberPatch(members, "2", { role: null, status: null })[1]).toEqual(members[1]);
    expect(applyMemberPatch(members, "nope", { role: "admin" })).toEqual(members);
  });
});

describe("invites", () => {
  const invites: Invite[] = [
    { id: "i1", kind: "invite", email: "x@example.test", role: "user", expires_at: "2030-01-02T00:00:00Z", created_at: null },
    { id: "i2", kind: "reset", email: "y@example.test", role: "agent", expires_at: "2030-01-02T00:00:00Z", created_at: null },
  ];

  it("removes one invite", () => {
    expect(withoutInvite(invites, "i1").map((i) => i.id)).toEqual(["i2"]);
    expect(withoutInvite(invites, "none")).toHaveLength(2);
  });

  it("names the two kinds of link", () => {
    expect(inviteKindLabel("invite")).toBe("Invitation");
    expect(inviteKindLabel("reset")).toBe("Password reset");
  });
});

describe("isNoop", () => {
  it("recognises a change to the value already set", () => {
    expect(isNoop(members[1]!, { role: "user" })).toBe(true);
    expect(isNoop(members[1]!, { role: "agent" })).toBe(false);
    expect(isNoop(members[1]!, { status: "active" })).toBe(true);
    expect(isNoop(members[1]!, {})).toBe(true);
  });
});
