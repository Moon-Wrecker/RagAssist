import { CircleCheck, CircleDashed, Circle, CircleX, RefreshCw, Trash2 } from "lucide-react";
import type { DocumentSummary, IngestionJob } from "@/api/documents";
import { DataTable, TableCaption, TBody, Td, Th, THead, Tr } from "@/components/data-table";
import { StatusMark } from "@/components/status-mark";
import { MenuItem, RowMenu } from "@/components/ui/dropdown-menu";
import { formatBytes, timeAgo } from "@/lib/format";
import { documentPhase, failureReason, statusLine, type DocumentPhase } from "./documents-logic";

function PhaseMark({ phase, label }: { phase: DocumentPhase; label: string }) {
  switch (phase) {
    case "queued":
      return <StatusMark icon={Circle} label={label} emphasis="normal" />;
    case "working":
      return <StatusMark icon={CircleDashed} label={label} emphasis="strong" />;
    case "done":
      return <StatusMark icon={CircleCheck} label={label} emphasis="muted" />;
    case "failed":
      return <StatusMark icon={CircleX} label={label} emphasis="alert" />;
  }
}

/** The documents on a thick surface: sticky header, hairline rows, status as a mono label, actions in a row menu. */
export function DocumentsTable({
  documents,
  jobs,
  onReindex,
  onDelete,
}: {
  documents: DocumentSummary[];
  /** Jobs we know about, by document id. A document without one shows its own status. */
  jobs: Record<string, IngestionJob | undefined>;
  onReindex: (doc: DocumentSummary) => void;
  onDelete: (doc: DocumentSummary) => void;
}) {
  return (
    <DataTable>
      <TableCaption>Documents the assistant answers from</TableCaption>
      <THead>
        <Tr className="hover:bg-transparent hover:shadow-none">
          <Th>Name</Th>
          <Th>Status</Th>
          <Th>Size</Th>
          <Th>Added</Th>
          <Th className="w-14">
            <span className="sr-only">Actions</span>
          </Th>
        </Tr>
      </THead>
      <TBody>
        {documents.map((doc) => {
          const phase = documentPhase(doc.status);
          const job = jobs[doc.document_id];
          const busy = phase === "queued" || phase === "working";
          return (
            <Tr key={doc.document_id}>
              <Td primary label="Name" className="max-w-[28rem] align-top">
                <span className="block font-medium break-words">{doc.filename}</span>
                {phase === "failed" ? (
                  <span className="mt-1.5 block border-l-2 border-dashed border-foreground pl-3 text-[0.8125rem] font-normal">
                    <span className="text-meta mr-2">Why it failed</span>
                    {failureReason(doc, job)}
                  </span>
                ) : null}
              </Td>
              <Td label="Status" className="align-top">
                <PhaseMark phase={phase} label={statusLine(doc, job)} />
              </Td>
              <Td label="Size" className="text-meta align-top text-muted-foreground">
                {formatBytes(doc.file_size_bytes)}
              </Td>
              <Td label="Added" className="text-meta align-top text-muted-foreground">
                {timeAgo(doc.created_at)}
              </Td>
              <Td className="align-top max-sm:justify-start sm:text-right">
                <RowMenu label={`Actions for ${doc.filename}`}>
                  <MenuItem disabled={busy} onSelect={() => onReindex(doc)}>
                    <RefreshCw aria-hidden />
                    Re-index
                  </MenuItem>
                  <MenuItem onSelect={() => onDelete(doc)}>
                    <Trash2 aria-hidden />
                    Delete
                  </MenuItem>
                </RowMenu>
              </Td>
            </Tr>
          );
        })}
      </TBody>
    </DataTable>
  );
}
