import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useReducer, useRef, useState } from "react";
import { deleteDocument, getIngestionJob, listDocuments, reindexDocument, uploadDocument, type DocumentList, type DocumentSummary, type IngestionJob } from "@/api/documents";
import { optimisticTarget, useOptimisticMutation } from "@/api/optimistic";
import { queryKeys } from "@/api/query-keys";
import { EmptyState, ErrorState } from "@/components/empty-state";
import { TableSkeleton } from "@/components/skeleton";
import { TableSurface } from "@/components/table-surface";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageFrame } from "@/components/page-frame";
import { FormMessage } from "@/features/auth/form-message";
import { actionError } from "@/lib/error-message";
import { DocumentsTable } from "./documents-table";
import { describeUploadError, isInFlight, phaseAnnouncement, type DocumentPhase, uploadReducer, withoutDocument, withRequeued } from "./documents-logic";
import { UploadZone } from "./upload-zone";
import { validateUpload } from "./upload-validation";

let nextUploadId = 0;

/**
 * Knowledge base (admin): upload, live indexing status, failure reasons, re-index and delete.
 * `job.updated` and `document.changed` events (useEvents) refetch the documents and the job we are watching.
 */
export function KnowledgePage() {
  const queryClient = useQueryClient();
  const documents = useQuery({ queryKey: queryKeys.documents, queryFn: listDocuments });
  const items = useMemo(() => documents.data?.items ?? [], [documents.data]);
  const [uploads, dispatch] = useReducer(uploadReducer, []);
  // The list does not carry job ids, so remember the ones we started (upload, re-index) to show their stage.
  const [jobIds, setJobIds] = useState<Record<string, string>>({});
  const [announcement, setAnnouncement] = useState("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  // The document stays set while the dialog animates closed, so its text does not vanish mid-fade.
  const [toDelete, setToDelete] = useState<DocumentSummary | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const watched = items.filter((doc) => isInFlight(doc) && jobIds[doc.document_id]);
  const jobQueries = useQueries({
    queries: watched.map((doc) => {
      const jobId = jobIds[doc.document_id]!;
      return { queryKey: queryKeys.ingestionJob(jobId), queryFn: () => getIngestionJob(jobId) };
    }),
  });
  const jobs: Record<string, IngestionJob | undefined> = {};
  watched.forEach((doc, index) => {
    jobs[doc.document_id] = jobQueries[index]?.data;
  });

  // Tell screen readers when a document finishes or fails, whether or not they are looking at the table. This is
  // derived while rendering (not in an effect): compare with the phases seen for the previous list.
  const [tracked, setTracked] = useState<{ items: DocumentSummary[]; phases: Record<string, DocumentPhase> }>({
    items: [],
    phases: {},
  });
  if (tracked.items !== items) {
    const { phases, message } = phaseAnnouncement(tracked.phases, items);
    setTracked({ items, phases });
    if (message) setAnnouncement(message);
  }

  async function handleFiles(files: File[]) {
    setActionMessage(null);
    for (const file of files) {
      const id = String(nextUploadId++);
      const check = validateUpload(file);
      if (!check.ok) {
        dispatch({ type: "add", entry: { id, name: file.name, size: file.size, state: "rejected", message: check.reason } });
        continue;
      }
      dispatch({ type: "add", entry: { id, name: file.name, size: file.size, state: "uploading", message: null } });
      try {
        // Send the type the extension implies, whatever the browser guessed.
        const result = await uploadDocument(new File([file], file.name, { type: check.mime }));
        setJobIds((current) => ({ ...current, [result.document_id]: result.job_id }));
        dispatch({ type: "done", id });
        setAnnouncement(`${file.name} uploaded. Indexing has started.`);
        void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      } catch (error) {
        dispatch({ type: "fail", id, message: describeUploadError(error, file.name) });
      }
    }
  }

  const listTarget = (apply: (cache: DocumentList, id: string) => DocumentList) =>
    optimisticTarget<DocumentList, string>(queryKeys.documents, apply);

  const reindex = useOptimisticMutation<string, { document_id: string; job_id: string }>({
    targets: [listTarget(withRequeued)],
    mutationFn: reindexDocument,
    onSuccess: (result) => {
      setJobIds((current) => ({ ...current, [result.document_id]: result.job_id }));
      setAnnouncement("Re-indexing has started.");
    },
    onError: (error) => setActionMessage(actionError(error, "re-index that document")),
  });

  const remove = useOptimisticMutation<string, unknown>({
    targets: [listTarget(withoutDocument)],
    mutationFn: deleteDocument,
    onSuccess: () => setAnnouncement("Document deleted."),
    onError: (error) => setActionMessage(actionError(error, "delete that document")),
  });

  function confirmDelete() {
    if (!toDelete) return;
    setActionMessage(null);
    remove.mutate(toDelete.document_id);
    setDeleteOpen(false);
  }

  const total = documents.data?.total ?? 0;

  return (
    <PageFrame
      title={<>Knowledge</>}
      headingRef={headingRef}
      mode="fill"
      actions={
        <Button variant="ghost" size="sm" onClick={() => void documents.refetch()} disabled={documents.isFetching}>
          {documents.isFetching ? "Refreshing" : "Refresh"}
        </Button>
      }
    >
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      <div className="flex h-full min-h-0 flex-col gap-3 px-(--gutter)">
        <div className="shrink-0">
          <UploadZone entries={uploads} onFiles={(files) => void handleFiles(files)} onDismiss={(id) => dispatch({ type: "dismiss", id })} />
          <FormMessage id="knowledge-action-error" message={actionMessage} />
        </div>

        <TableSurface aria-label="Documents" className="shrink grow-0">
          {documents.isPending ? (
            <TableSkeleton label="Loading documents" columns={5} />
          ) : documents.isError ? (
            <ErrorState what="The documents" onRetry={() => void documents.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState title="No documents yet." hint="Add a PDF, Markdown, HTML or CSV file." />
          ) : (
            <DocumentsTable
              documents={items}
              jobs={jobs}
              onReindex={(doc) => {
                setActionMessage(null);
                reindex.mutate(doc.document_id);
              }}
              onDelete={(doc) => {
                setToDelete(doc);
                setDeleteOpen(true);
              }}
            />
          )}
          {documents.isSuccess && total > items.length ? (
            <p className="text-meta border-t border-border p-4 text-muted-foreground">
              Showing the newest {items.length} of {total}.
            </p>
          ) : null}
        </TableSurface>
      </div>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent
          onCloseAutoFocus={(event) => {
            // Return focus to the row menu that led here; if its row is gone (deleted), go to the page title.
            event.preventDefault();
            const name = toDelete ? `Actions for ${toDelete.filename}` : "";
            const trigger = name ? document.querySelector<HTMLElement>(`[aria-label="${CSS.escape(name)}"]`) : null;
            (trigger ?? headingRef.current)?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>Delete this document?</DialogTitle>
            <DialogDescription>
              <span className="font-medium text-foreground break-all">{toDelete?.filename}</span> is removed, and the assistant stops using it. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 px-6 pt-5 pb-6">
            <DialogClose asChild>
              <Button variant="secondary">Keep it</Button>
            </DialogClose>
            <Button onClick={confirmDelete}>Delete document</Button>
          </div>
        </DialogContent>
      </Dialog>
    </PageFrame>
  );
}
