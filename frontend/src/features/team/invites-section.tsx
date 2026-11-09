import { useId, useState, type FormEvent } from "react";
import type { Invite } from "@/api/team";
import type { Role } from "@/api/types";
import { DataTable, TableCaption, TBody, Td, Th, THead, Tr } from "@/components/data-table";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { FormMessage } from "@/features/auth/form-message";
import { timeUntil } from "@/lib/format";
import { inviteKindLabel, ROLE_HINTS, ROLE_LABELS, ROLE_ORDER } from "./team-logic";

export function InviteForm({
  onCreate,
  pending,
  error,
}: {
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
    if (created) setEmail("");
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4 p-5 sm:p-6">
      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_14rem_auto] sm:items-start">
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
        </div>
        <Button type="submit" disabled={pending} className="sm:mt-[1.625rem]">
          {pending ? "Creating" : "Create invite link"}
        </Button>
      </div>
      <p className="text-[0.8125rem] text-muted-foreground">
        {ROLE_HINTS[role]} No email is sent: you copy the link and give it to them yourself. It is shown once.
      </p>
      <FormMessage id={errorId} message={error} />
    </form>
  );
}

export function InvitesTable({ invites, onRevoke }: { invites: Invite[]; onRevoke: (invite: Invite, trigger: HTMLElement) => void }) {
  return (
    <DataTable>
      <TableCaption>Pending invitations and reset links</TableCaption>
      <THead>
        <Tr className="hover:bg-transparent">
          <Th>Email</Th>
          <Th>Type</Th>
          <Th>Role</Th>
          <Th>Expires</Th>
          <Th>
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
            <Td label="Type" className="font-mono text-xs">
              {inviteKindLabel(invite.kind)}
            </Td>
            <Td label="Role" className="font-mono text-xs">
              {ROLE_LABELS[invite.role]}
            </Td>
            <Td label="Expires" className="font-mono text-xs text-muted-foreground">
              {timeUntil(invite.expires_at)}
            </Td>
            <Td className="max-sm:justify-start sm:text-right">
              <Button
                variant="outline"
                size="sm"
                onClick={(event) => onRevoke(invite, event.currentTarget)}
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
