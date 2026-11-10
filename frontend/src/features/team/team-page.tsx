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
import { Plus } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/empty-state";
import { TableSkeleton } from "@/components/skeleton";
import { TableSurface } from "@/components/table-surface";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageFrame } from "@/components/page-frame";
import { FormMessage } from "@/features/auth/form-message";
import { actionError } from "@/lib/error-message";
import { InviteDialog, InvitesTable } from "./invites-section";
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
  const [inviteOpen, setInviteOpen] = useState(false);
  const [issued, setIssued] = useState<Issued | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [toDeactivate, setToDeactivate] = useState<Member | null>(null);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
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
    <PageFrame
      title={<>Team</>}
      headingRef={headingRef}
      mode="fill"
      actions={
        <Button size="sm" onClick={() => setInviteOpen(true)}>
          <Plus aria-hidden />
          Invite
        </Button>
      }
    >
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      <div className="flex h-full min-h-0 flex-col gap-3 px-(--gutter)">
        <FormMessage id="team-action-error" message={message} />

        <TableSurface aria-label="Members" className="flex-1">
          {members.isPending ? (
            <TableSkeleton label="Loading members" columns={4} />
          ) : members.isError ? (
            <ErrorState what="The members" onRetry={() => void members.refetch()} />
          ) : memberList.length === 0 ? (
            <EmptyState title="No members yet." />
          ) : (
            <MembersTable
              members={memberList}
              selfId={user.id}
              onRole={(member, role) => changeMember(member, { role })}
              onDeactivate={(member) => {
                setToDeactivate(member);
                setDeactivateOpen(true);
              }}
              onReactivate={(member) => changeMember(member, { status: "active" })}
              onResetLink={(member) => void resetLink(member)}
            />
          )}
        </TableSurface>

        <section aria-label="Pending links" className="flex max-h-[38%] min-h-0 shrink flex-col gap-1.5">
          <h2 className="text-meta px-4 text-muted-foreground">
            Pending links {invites.isSuccess ? <span>{inviteList.length}</span> : null}
          </h2>
          {invites.isPending ? (
            <TableSurface aria-label="Loading pending links">
              <TableSkeleton label="Loading pending links" columns={5} rows={2} />
            </TableSurface>
          ) : invites.isError ? (
            <TableSurface aria-label="Pending links could not be loaded">
              <ErrorState what="The pending links" onRetry={() => void invites.refetch()} className="py-8" />
            </TableSurface>
          ) : inviteList.length === 0 ? (
            <p className="px-4 pb-1 text-sm text-muted-foreground">No links waiting.</p>
          ) : (
            <TableSurface aria-label="Pending links table">
              <InvitesTable
                invites={inviteList}
                onRevoke={(invite) => {
                  setMessage(null);
                  revoke.mutate(invite);
                }}
              />
            </TableSurface>
          )}
        </section>
      </div>

      <InviteDialog
        open={inviteOpen}
        onOpenChange={(open) => {
          setInviteOpen(open);
          if (!open) setInviteError(null);
        }}
        onCreate={create}
        pending={creating}
        error={inviteError}
      />

      <IssuedLinkDialog link={issued?.link ?? null} kind={issued?.kind ?? "invite"} onClose={() => setIssued(null)} />

      <Dialog open={deactivateOpen} onOpenChange={setDeactivateOpen}>
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const name = toDeactivate ? `Actions for ${toDeactivate.email}` : "";
            const trigger = name ? document.querySelector<HTMLElement>(`[aria-label="${CSS.escape(name)}"]`) : null;
            (trigger ?? headingRef.current)?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>Deactivate this member?</DialogTitle>
            <DialogDescription>
              <span className="font-medium text-foreground break-all">{toDeactivate?.email}</span> is signed
              out and cannot sign in until you reactivate them.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 px-6 pt-5 pb-6">
            <DialogClose asChild>
              <Button variant="secondary">Keep them active</Button>
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
    </PageFrame>
  );
}
