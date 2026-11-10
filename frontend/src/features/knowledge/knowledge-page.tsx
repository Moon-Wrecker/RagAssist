import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useReducer, useRef, useState } from "react";
import { deleteDocument, getIngestionJob, listDocuments, reindexDocument, uploadDocument, type DocumentList, type DocumentSummary, type IngestionJob } from "@/api/documents";
import { optimisticTarget, useOptimisticMutation } from "@/api/optimistic";
import { queryKeys } from "@/api/query-keys";
import { Panel } from "@/components/panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
  const deleteTrigger = useRef<HTMLElement | null>(null);
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
    <div className="flex flex-col gap-6">
      <header>
        <h1 ref={headingRef} tabIndex={-1} className="font-heading text-5xl outline-none sm:text-6xl">
          Knowledge
        </h1>
        <p className="mt-3 max-w-prose text-muted-foreground">
          The documents the assistant answers from. Add a file and it is read, split into passages and indexed; you can
          watch each one finish here.
        </p>
        <p className="sr-only" role="status" aria-live="polite">
          {announcement}
        </p>
      </header>

      <Panel className="p-5 sm:p-6">
        <h2 className="mb-4 text-sm font-medium">Add documents</h2>
        <UploadZone entries={uploads} onFiles={(files) => void handleFiles(files)} onDismiss={(id) => dispatch({ type: "dismiss", id })} />
      </Panel>

      <section aria-label="Documents" className="glass-1 overflow-hidden rounded-3xl">
        <div className="flex items-center justify-between gap-3 border-b px-5 py-4 sm:px-6">
          <h2 className="text-sm font-medium">
            Documents <span className="font-mono text-xs text-muted-foreground">{documents.isSuccess ? total : ""}</span>
          </h2>
          <Button variant="ghost" size="sm" onClick={() => void documents.refetch()} disabled={documents.isFetching}>
            {documents.isFetching ? "Refreshing" : "Refresh"}
          </Button>
        </div>
        <FormMessage id="knowledge-action-error" message={actionMessage} />
        {documents.isPending ? (
          <p className="p-6 text-sm text-muted-foreground" role="status">
            Loading documents
          </p>
        ) : documents.isError ? (
          <div className="flex flex-col items-start gap-3 p-6" role="alert">
            <p className="text-sm">The documents could not be loaded.</p>
            <Button variant="secondary" size="sm" onClick={() => void documents.refetch()}>
              Try again
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="p-6">
            <p className="font-medium">No documents yet.</p>
            <p className="mt-2 max-w-prose text-sm text-muted-foreground">
              Add a PDF, Markdown, HTML or CSV file above. Until you do, the assistant has nothing of yours to answer from.
            </p>
          </div>
        ) : (
          <DocumentsTable
            documents={items}
            jobs={jobs}
            onReindex={(doc) => {
              setActionMessage(null);
              reindex.mutate(doc.document_id);
            }}
            onDelete={(doc, trigger) => {
              deleteTrigger.current = trigger;
              setToDelete(doc);
              setDeleteOpen(true);
            }}
          />
        )}
        {documents.isSuccess && total > items.length ? (
          <p className="border-t p-4 font-mono text-xs text-muted-foreground">
            Showing the newest {items.length} of {total}.
          </p>
        ) : null}
      </section>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent
          onCloseAutoFocus={(event) => {
            // Return focus to the button that opened the dialog; if its row is gone (deleted), go to the page title.
            event.preventDefault();
            const trigger = deleteTrigger.current;
            (trigger?.isConnected ? trigger : headingRef.current)?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>Delete this document?</DialogTitle>
            <DialogDescription>
              <span className="font-medium text-foreground break-all">{toDelete?.filename}</span> and its
              indexed passages are removed. The assistant stops answering from it. This cannot be undone.
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
    </div>
  );
}
