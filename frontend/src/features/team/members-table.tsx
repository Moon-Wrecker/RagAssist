import { CircleDashed, CircleDot, CircleSlash } from "lucide-react";
import type { Member } from "@/api/team";
import type { Role } from "@/api/types";
import { DataTable, TableCaption, TBody, Td, Th, THead, Tr } from "@/components/data-table";
import { StatusMark } from "@/components/status-mark";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { memberState, ROLE_LABELS, ROLE_ORDER, STATE_LABELS } from "./team-logic";

function StateMark({ member }: { member: Member }) {
  const state = memberState(member);
  const label = STATE_LABELS[state];
  switch (state) {
    case "active":
      return <StatusMark icon={CircleDot} label={label} emphasis="normal" />;
    case "deactivated":
      return <StatusMark icon={CircleSlash} label={label} emphasis="muted" />;
    case "awaiting":
      return <StatusMark icon={CircleDashed} label={label} emphasis="muted" />;
  }
}

export function MembersTable({
  members,
  selfId,
  onRole,
  onDeactivate,
  onReactivate,
  onResetLink,
}: {
  members: Member[];
  selfId: string;
  onRole: (member: Member, role: Role) => void;
  onDeactivate: (member: Member, trigger: HTMLElement) => void;
  onReactivate: (member: Member) => void;
  onResetLink: (member: Member) => void;
}) {
  return (
    <DataTable>
      <TableCaption>Members of this workspace</TableCaption>
      <THead>
        <Tr className="hover:bg-transparent">
          <Th>Member</Th>
          <Th>Role</Th>
          <Th>Status</Th>
          <Th>
            <span className="sr-only">Actions</span>
          </Th>
        </Tr>
      </THead>
      <TBody>
        {members.map((member) => {
          const self = member.id === selfId;
          const deactivated = member.status === "disabled";
          return (
            <Tr key={member.id}>
              <Td primary label="Member" className="break-all">
                {member.email}
                {self ? <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">you</span> : null}
              </Td>
              <Td label="Role" className="sm:w-48">
                <Select
                  aria-label={`Role for ${member.email}`}
                  value={member.role}
                  disabled={self}
                  title={self ? "You cannot change your own role here." : undefined}
                  onChange={(event) => onRole(member, event.target.value as Role)}
                  className="h-9 max-sm:w-44"
                >
                  {ROLE_ORDER.map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </option>
                  ))}
                </Select>
              </Td>
              <Td label="Status">
                <StateMark member={member} />
              </Td>
              <Td className="max-sm:justify-start sm:text-right">
                <span className="inline-flex flex-wrap gap-1.5 sm:justify-end">
                  <Button variant="outline" size="sm" onClick={() => onResetLink(member)} aria-label={`Create a password reset link for ${member.email}`} disabled={deactivated}>
                    Reset link
                  </Button>
                  {deactivated ? (
                    <Button variant="outline" size="sm" onClick={() => onReactivate(member)} aria-label={`Reactivate ${member.email}`}>
                      Reactivate
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={self}
                      title={self ? "You cannot deactivate yourself." : undefined}
                      onClick={(event) => onDeactivate(member, event.currentTarget)}
                      aria-label={`Deactivate ${member.email}`}
                    >
                      Deactivate
                    </Button>
                  )}
                </span>
              </Td>
            </Tr>
          );
        })}
      </TBody>
    </DataTable>
  );
}
