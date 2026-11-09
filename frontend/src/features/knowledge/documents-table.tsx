import { CircleCheck, CircleDashed, Circle, CircleX, RefreshCw, Trash2 } from "lucide-react";
import type { DocumentSummary, IngestionJob } from "@/api/documents";
import { DataTable, TableCaption, TBody, Td, Th, THead, Tr } from "@/components/data-table";
import { StatusMark } from "@/components/status-mark";
import { Button } from "@/components/ui/button";
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
  onDelete: (doc: DocumentSummary, trigger: HTMLElement) => void;
}) {
  return (
    <DataTable>
      <TableCaption>Documents the assistant answers from</TableCaption>
      <THead>
        <Tr className="hover:bg-transparent">
          <Th>Name</Th>
          <Th>Status</Th>
          <Th>Size</Th>
          <Th>Added</Th>
          <Th>
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
                    <span className="mr-2 font-mono text-xs">Why it failed</span>
                    {failureReason(doc, job)}
                  </span>
                ) : null}
              </Td>
              <Td label="Status" className="align-top">
                <PhaseMark phase={phase} label={statusLine(doc, job)} />
              </Td>
              <Td label="Size" className="align-top font-mono text-xs text-muted-foreground">
                {formatBytes(doc.file_size_bytes)}
              </Td>
              <Td label="Added" className="align-top font-mono text-xs text-muted-foreground">
                {timeAgo(doc.created_at)}
              </Td>
              <Td className="align-top max-sm:justify-start sm:text-right">
                <span className="inline-flex gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onReindex(doc)}
                    disabled={busy}
                    aria-label={`Re-index ${doc.filename}`}
                    title={busy ? "Already being indexed" : undefined}
                  >
                    <RefreshCw aria-hidden />
                    Re-index
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={(event) => onDelete(doc, event.currentTarget)}
                    aria-label={`Delete ${doc.filename}`}
                  >
                    <Trash2 aria-hidden />
                    Delete
                  </Button>
                </span>
              </Td>
            </Tr>
          );
        })}
      </TBody>
    </DataTable>
  );
}
