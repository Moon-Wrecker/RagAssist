import { CircleDashed, CircleDot, CircleSlash, KeyRound, UserCheck, UserX } from "lucide-react";
import type { Member } from "@/api/team";
import type { Role } from "@/api/types";
import { DataTable, TableCaption, TBody, Td, Th, THead, Tr } from "@/components/data-table";
import { StatusMark } from "@/components/status-mark";
import { MenuItem, RowMenu } from "@/components/ui/dropdown-menu";
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

/** Members on a thick surface: role as an inline select, status as a mono label, actions in a row menu. */
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
  onDeactivate: (member: Member) => void;
  onReactivate: (member: Member) => void;
  onResetLink: (member: Member) => void;
}) {
  return (
    <DataTable>
      <TableCaption>Members of this workspace</TableCaption>
      <THead>
        <Tr className="hover:bg-transparent hover:shadow-none">
          <Th>Member</Th>
          <Th>Role</Th>
          <Th>Status</Th>
          <Th className="w-14">
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
                {self ? <span className="text-meta ml-2 font-normal text-muted-foreground">you</span> : null}
              </Td>
              <Td label="Role" className="sm:w-52">
                <Select
                  inline
                  aria-label={`Role for ${member.email}`}
                  value={member.role}
                  disabled={self}
                  title={self ? "You cannot change your own role here." : undefined}
                  onChange={(event) => onRole(member, event.target.value as Role)}
                  className="max-sm:w-44"
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
                <RowMenu label={`Actions for ${member.email}`}>
                  <MenuItem disabled={deactivated} onSelect={() => onResetLink(member)}>
                    <KeyRound aria-hidden />
                    Reset password link
                  </MenuItem>
                  {deactivated ? (
                    <MenuItem onSelect={() => onReactivate(member)}>
                      <UserCheck aria-hidden />
                      Reactivate
                    </MenuItem>
                  ) : (
                    <MenuItem disabled={self} onSelect={() => onDeactivate(member)}>
                      <UserX aria-hidden />
                      Deactivate
                    </MenuItem>
                  )}
                </RowMenu>
              </Td>
            </Tr>
          );
        })}
      </TBody>
    </DataTable>
  );
}
