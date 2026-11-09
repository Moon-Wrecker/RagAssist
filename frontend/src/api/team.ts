import { apiFetch, apiJson, jsonBody } from "./http";
import { apiErrorFromResponse } from "./errors";
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Member = Schemas["MemberOut"];
export type MemberPatch = Schemas["MemberPatch"];
export type Invite = Schemas["InviteOut"];
export type IssuedLink = Schemas["IssuedLinkOut"];
export type InviteRequest = Schemas["InviteRequest"];

export function listMembers(): Promise<Member[]> {
  return apiJson<Member[]>("/v1/team/members");
}

export function patchMember(userId: string, patch: MemberPatch): Promise<Member> {
  return apiJson<Member>(`/v1/team/members/${encodeURIComponent(userId)}`, { method: "PATCH", ...jsonBody(patch) });
}

/** The link is in the response once; the server keeps only its hash. */
export function issueResetLink(userId: string): Promise<IssuedLink> {
  return apiJson<IssuedLink>(`/v1/team/members/${encodeURIComponent(userId)}/reset-link`, { method: "POST" });
}

export function listInvites(): Promise<Invite[]> {
  return apiJson<Invite[]>("/v1/team/invites");
}

export function createInvite(request: InviteRequest): Promise<IssuedLink> {
  return apiJson<IssuedLink>("/v1/team/invites", { method: "POST", ...jsonBody(request) });
}

export async function revokeInvite(inviteId: string): Promise<void> {
  const response = await apiFetch(`/v1/team/invites/${encodeURIComponent(inviteId)}`, { method: "DELETE" });
  if (!response.ok) throw await apiErrorFromResponse(response);
}
