import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { optimisticTarget, useOptimisticMutation } from "@/api/optimistic";
import { queryKeys } from "@/api/query-keys";
import {
  createInvite,
  issueResetLink,
  listInvites,
  listMembers,
  patchMember,
  revokeInvite,
  type Invite,
  type IssuedLink,
  type Member,
  type MemberPatch,
} from "@/api/team";
import type { Role } from "@/api/types";
import { useSignedIn } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FormMessage } from "@/features/auth/form-message";
import { actionError } from "@/lib/error-message";
import { InviteForm, InvitesTable } from "./invites-section";
import { IssuedLinkDialog, type IssuedKind } from "./issued-link-dialog";
import { MembersTable } from "./members-table";
import { applyMemberPatch, isNoop, withoutInvite } from "./team-logic";

interface Issued {
  link: IssuedLink;
  kind: IssuedKind;
}

/** Team (admin): members and roles, deactivate and reactivate, invitations, one-time links. */
export function TeamPage() {
  const { user } = useSignedIn();
  const queryClient = useQueryClient();
  const members = useQuery({ queryKey: queryKeys.teamMembers, queryFn: listMembers });
  const invites = useQuery({ queryKey: queryKeys.teamInvites, queryFn: listInvites });
  const [issued, setIssued] = useState<Issued | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [toDeactivate, setToDeactivate] = useState<Member | null>(null);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const trigger = useRef<HTMLElement | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const change = useOptimisticMutation<{ id: string; patch: MemberPatch }, Member>({
    targets: [
      optimisticTarget<Member[], { id: string; patch: MemberPatch }>(queryKeys.teamMembers, (cache, { id, patch }) =>
        applyMemberPatch(cache, id, patch),
      ),
    ],
    mutationFn: ({ id, patch }) => patchMember(id, patch),
    onSuccess: (member, { patch }) => {
      if (patch.status === "disabled") setAnnouncement(`${member.email} is deactivated.`);
      else if (patch.status === "active") setAnnouncement(`${member.email} is active again.`);
      else setAnnouncement(`${member.email} is now ${member.role}.`);
    },
    onError: (error) => setMessage(actionError(error, "change that member")),
  });

  const revoke = useOptimisticMutation<Invite, void>({
    targets: [optimisticTarget<Invite[], Invite>(queryKeys.teamInvites, (cache, invite) => withoutInvite(cache, invite.id))],
    mutationFn: (invite) => revokeInvite(invite.id),
    onSuccess: () => setAnnouncement("Link revoked. It no longer works."),
    onError: (error) => setMessage(actionError(error, "revoke that link")),
  });

  function changeMember(member: Member, patch: MemberPatch) {
    setMessage(null);
    if (isNoop(member, patch)) return;
    change.mutate({ id: member.id, patch });
  }

  const [creating, setCreating] = useState(false);
  async function create(email: string, role: Role): Promise<boolean> {
    setCreating(true);
    setInviteError(null);
    try {
      const link = await createInvite({ email, role });
      setIssued({ link, kind: "invite" });
      void queryClient.invalidateQueries({ queryKey: queryKeys.teamInvites });
      return true;
    } catch (error) {
      setInviteError(actionError(error, "create that invitation"));
      return false;
    } finally {
      setCreating(false);
    }
  }

  async function resetLink(member: Member) {
    setMessage(null);
    try {
      const link = await issueResetLink(member.id);
      setIssued({ link, kind: "reset" });
      void queryClient.invalidateQueries({ queryKey: queryKeys.teamInvites });
    } catch (error) {
      setMessage(actionError(error, "create a reset link"));
    }
  }

  const memberList = members.data ?? [];
  const inviteList = invites.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 ref={headingRef} tabIndex={-1} className="font-heading text-5xl outline-none sm:text-6xl">
          Team
        </h1>
        <p className="mt-3 max-w-prose text-muted-foreground">
          Who can sign in to this workspace and what they can do. There is no email service: when you invite someone or
          reset a password you get a link to give them yourself.
        </p>
        <p className="sr-only" role="status" aria-live="polite">
          {announcement}
        </p>
      </header>

      <FormMessage id="team-action-error" message={message} />

      <section aria-label="Members" className="glass-1 overflow-hidden rounded-3xl">
        <div className="flex items-center justify-between gap-3 border-b px-5 py-4 sm:px-6">
          <h2 className="text-sm font-medium">
            Members <span className="font-mono text-xs text-muted-foreground">{members.isSuccess ? memberList.length : ""}</span>
          </h2>
        </div>
        {members.isPending ? (
          <p className="p-6 text-sm text-muted-foreground" role="status">
            Loading members
          </p>
        ) : members.isError ? (
          <div className="flex flex-col items-start gap-3 p-6" role="alert">
            <p className="text-sm">The members could not be loaded.</p>
            <Button variant="outline" size="sm" onClick={() => void members.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <MembersTable
            members={memberList}
            selfId={user.id}
            onRole={(member, role) => changeMember(member, { role })}
            onDeactivate={(member, element) => {
              trigger.current = element;
              setToDeactivate(member);
              setDeactivateOpen(true);
            }}
            onReactivate={(member) => changeMember(member, { status: "active" })}
            onResetLink={(member) => void resetLink(member)}
          />
        )}
      </section>

      <section aria-label="Invitations" className="glass-1 overflow-hidden rounded-3xl">
        <div className="border-b px-5 py-4 sm:px-6">
          <h2 className="text-sm font-medium">Invite someone</h2>
        </div>
        <InviteForm onCreate={create} pending={creating} error={inviteError} />
        <div className="border-t px-5 py-4 sm:px-6">
          <h2 className="text-sm font-medium">
            Pending links <span className="font-mono text-xs text-muted-foreground">{invites.isSuccess ? inviteList.length : ""}</span>
          </h2>
        </div>
        {invites.isPending ? (
          <p className="px-5 pb-6 sm:px-6 text-sm text-muted-foreground" role="status">
            Loading pending links
          </p>
        ) : invites.isError ? (
          <div className="flex flex-col items-start gap-3 px-5 pb-6 sm:px-6" role="alert">
            <p className="text-sm">The pending links could not be loaded.</p>
            <Button variant="outline" size="sm" onClick={() => void invites.refetch()}>
              Try again
            </Button>
          </div>
        ) : inviteList.length === 0 ? (
          <div className="px-5 pb-6 sm:px-6">
            <p className="text-sm font-medium">No links are waiting.</p>
            <p className="mt-1 max-w-prose text-sm text-muted-foreground">
              Create an invite above, or a reset link from a member's row. Links that are unused appear here until they
              expire. A link cannot be shown again, so revoke it and make a new one if it gets lost.
            </p>
          </div>
        ) : (
          <InvitesTable invites={inviteList} onRevoke={(invite) => { setMessage(null); revoke.mutate(invite); }} />
        )}
      </section>

      <IssuedLinkDialog link={issued?.link ?? null} kind={issued?.kind ?? "invite"} onClose={() => setIssued(null)} />

      <Dialog open={deactivateOpen} onOpenChange={setDeactivateOpen}>
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            (trigger.current?.isConnected ? trigger.current : headingRef.current)?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>Deactivate this member?</DialogTitle>
            <DialogDescription>
              <span className="font-medium text-foreground break-all">{toDeactivate?.email}</span> is signed
              out and cannot sign in again until you reactivate them. A page they already have open may keep working for
              a few minutes.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 px-6 pt-5 pb-6">
            <DialogClose asChild>
              <Button variant="outline">Keep them active</Button>
            </DialogClose>
            <Button
              onClick={() => {
                if (toDeactivate) changeMember(toDeactivate, { status: "disabled" });
                setDeactivateOpen(false);
              }}
            >
              Deactivate
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
