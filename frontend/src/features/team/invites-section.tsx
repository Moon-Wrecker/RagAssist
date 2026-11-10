import { useId, useState, type FormEvent } from "react";
import type { Invite } from "@/api/team";
import type { Role } from "@/api/types";
import { DataTable, TableCaption, TBody, Td, Th, THead, Tr } from "@/components/data-table";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { FormMessage } from "@/features/auth/form-message";
import { timeUntil } from "@/lib/format";
import { inviteKindLabel, ROLE_HINTS, ROLE_LABELS, ROLE_ORDER } from "./team-logic";

/** The dialog behind the one primary button on this page. It stays open on an error so the address can be fixed. */
export function InviteDialog({
  open,
  onOpenChange,
  onCreate,
  pending,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (email: string, role: Role) => Promise<boolean>;
  pending: boolean;
  error: string | null;
}) {
  const roleId = useId();
  const errorId = useId();
  const [role, setRole] = useState<Role>("user");
  const [email, setEmail] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const created = await onCreate(email.trim(), role);
    if (created) {
      setEmail("");
      onOpenChange(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite someone</DialogTitle>
          <DialogDescription>Invite people with a link. Links are shown once.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-5 px-6 pt-5 pb-6">
          <FormField
            label="Email address"
            type="email"
            name="invite-email"
            autoComplete="off"
            required
            maxLength={254}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            invalid={error !== null}
            errorId={errorId}
          />
          <div className="flex flex-col gap-2">
            <Label htmlFor={roleId}>Role</Label>
            <Select id={roleId} value={role} onChange={(event) => setRole(event.target.value as Role)}>
              {ROLE_ORDER.map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABELS[value]}
                </option>
              ))}
            </Select>
            <p className="text-[0.8125rem] text-muted-foreground">{ROLE_HINTS[role]}</p>
          </div>
          <FormMessage id={errorId} message={error} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={pending}>
              {pending ? "Creating" : "Create invite link"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Pending links: a small table of the same style. One quiet action per row, so it is a ghost button, not a menu. */
export function InvitesTable({ invites, onRevoke }: { invites: Invite[]; onRevoke: (invite: Invite) => void }) {
  return (
    <DataTable>
      <TableCaption>Pending invitations and reset links</TableCaption>
      <THead>
        <Tr className="hover:bg-transparent hover:shadow-none">
          <Th>Email</Th>
          <Th>Type</Th>
          <Th>Role</Th>
          <Th>Expires</Th>
          <Th className="w-24">
            <span className="sr-only">Actions</span>
          </Th>
        </Tr>
      </THead>
      <TBody>
        {invites.map((invite) => (
          <Tr key={invite.id}>
            <Td primary label="Email" className="break-all">
              {invite.email}
            </Td>
            <Td label="Type" className="text-meta">
              {inviteKindLabel(invite.kind)}
            </Td>
            <Td label="Role" className="text-meta">
              {ROLE_LABELS[invite.role]}
            </Td>
            <Td label="Expires" className="text-meta text-muted-foreground">
              {timeUntil(invite.expires_at)}
            </Td>
            <Td className="max-sm:justify-start sm:text-right">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onRevoke(invite)}
                aria-label={`Revoke the ${inviteKindLabel(invite.kind).toLowerCase()} for ${invite.email}`}
              >
                Revoke
              </Button>
            </Td>
          </Tr>
        ))}
      </TBody>
    </DataTable>
  );
}
