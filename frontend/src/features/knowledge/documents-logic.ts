import { ApiError, NetworkError } from "@/api/errors";
import type { DocumentList, DocumentSummary, IngestionJob } from "@/api/documents";
import { formatBytes } from "@/lib/format";
import { MAX_UPLOAD_BYTES } from "./upload-validation";

/** Pure document, job-stage and upload-queue logic. No React, no network. */

export type DocumentPhase = "queued" | "working" | "done" | "failed";

/** The document statuses the API uses (queued, pending, processing, completed, failed) as four phases. */
export function documentPhase(status: string): DocumentPhase {
  switch (status) {
    case "queued":
    case "pending":
      return "queued";
    case "completed":
      return "done";
    case "failed":
      return "failed";
    default:
      return "working";
  }
}

export function isInFlight(doc: Pick<DocumentSummary, "status">): boolean {
  const phase = documentPhase(doc.status);
  return phase === "queued" || phase === "working";
}

export const PHASE_LABELS: Record<DocumentPhase, string> = {
  queued: "Queued",
  working: "Indexing",
  done: "Ready",
  failed: "Failed",
};

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting in the queue",
  parsing: "Reading the file",
  chunking: "Splitting into passages",
  embedding: "Computing embeddings",
  indexing: "Saving to the index",
  completed: "Ready",
  failed: "Failed",
};

/** What an ingestion job is doing right now, in words. Unknown stages are shown as they come. */
export function jobStageLabel(status: string): string {
  return STAGE_LABELS[status] ?? status;
}

/** The stage to show for a document: the job's, when we know it and it is still moving; else the document's own. */
export function statusLine(doc: DocumentSummary, job: IngestionJob | undefined): string {
  const phase = documentPhase(doc.status);
  if ((phase === "queued" || phase === "working") && job && job.document_id === doc.document_id) {
    return jobStageLabel(job.status);
  }
  return PHASE_LABELS[phase];
}

/** Why a document failed: the document's own message, else its job's, else a plain fallback. */
export function failureReason(doc: DocumentSummary, job: IngestionJob | undefined): string {
  return (
    doc.error_message?.trim() ||
    (job && job.document_id === doc.document_id ? job.error_message?.trim() : "") ||
    "The reason was not recorded. Try re-indexing; if it fails again, check the file opens normally."
  );
}

/**
 * Compares the documents with the phases seen last time. Returns the phases now and, if a document that was
 * being indexed has finished or failed, a sentence for the screen-reader live region. The first call (no earlier
 * phases) announces nothing.
 */
export function phaseAnnouncement(
  before: Record<string, DocumentPhase>,
  docs: readonly DocumentSummary[],
): { phases: Record<string, DocumentPhase>; message: string | null } {
  const phases: Record<string, DocumentPhase> = {};
  let message: string | null = null;
  for (const doc of docs) {
    const phase = documentPhase(doc.status);
    phases[doc.document_id] = phase;
    const was = before[doc.document_id];
    if (was && was !== phase) {
      if (phase === "done") message = `${doc.filename} is ready.`;
      if (phase === "failed") message = `${doc.filename} failed to index.`;
    }
  }
  return { phases, message };
}

// --- optimistic updates ---------------------------------------------------------------------------------------

export function withoutDocument(list: DocumentList, documentId: string): DocumentList {
  const items = list.items.filter((doc) => doc.document_id !== documentId);
  return { ...list, items, total: Math.max(0, list.total - (list.items.length - items.length)) };
}

/** A re-index puts the document back in the queue at once; the server's list replaces this when it arrives. */
export function withRequeued(list: DocumentList, documentId: string): DocumentList {
  return {
    ...list,
    items: list.items.map((doc) =>
      doc.document_id === documentId ? { ...doc, status: "queued", error_message: null } : doc,
    ),
  };
}

// --- upload queue ---------------------------------------------------------------------------------------------

export type UploadState = "uploading" | "failed" | "rejected";

export interface UploadEntry {
  id: string;
  name: string;
  size: number;
  state: UploadState;
  message: string | null;
}

export type UploadAction =
  | { type: "add"; entry: UploadEntry }
  | { type: "fail"; id: string; message: string }
  | { type: "done"; id: string }
  | { type: "dismiss"; id: string }
  | { type: "clear" };

/** Entries are removed when their upload succeeds (the document row takes over); failures stay until dismissed. */
export function uploadReducer(state: UploadEntry[], action: UploadAction): UploadEntry[] {
  switch (action.type) {
    case "add":
      return [...state, action.entry];
    case "fail":
      return state.map((entry) => (entry.id === action.id ? { ...entry, state: "failed", message: action.message } : entry));
    case "done":
    case "dismiss":
      return state.filter((entry) => entry.id !== action.id);
    case "clear":
      return [];
  }
}

/** Plain-language reason an upload failed, from the status the API answered with. */
export function describeUploadError(error: unknown, name: string): string {
  if (error instanceof NetworkError) return `${name} could not be sent. Check your connection and try again.`;
  if (error instanceof ApiError) {
    switch (error.status) {
      case 400:
        return `${name} is empty. Choose a file that has content.`;
      case 401:
        return `Your session ended before ${name} was sent. Sign in again.`;
      case 403:
        return "Only workspace admins can upload documents.";
      case 413:
        return `${name} is larger than the ${formatBytes(MAX_UPLOAD_BYTES)} limit.`;
      case 415:
        return `${name} is not a supported type. Use PDF, Markdown, HTML or CSV.`;
      case 429:
        return "Too many uploads at once. Wait a moment and try again.";
    }
    if (error.status < 500 && error.detail) return error.detail;
  }
  return `${name} could not be uploaded. Try again in a moment.`;
}
