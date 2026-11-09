import { apiErrorFromResponse } from "./errors";
import { apiFetch, apiJson } from "./http";
import type { components } from "./schema";

type Schemas = components["schemas"];

export type DocumentSummary = Schemas["DocumentSummary"];
export type DocumentList = Schemas["DocumentListResponse"];
export type UploadResult = Schemas["DocumentUploadResponse"];
export type IngestionJob = Schemas["IngestionJobResponse"];

/** The API caps a page at 100. */
export const DOCUMENT_PAGE_SIZE = 100;

export function listDocuments(): Promise<DocumentList> {
  return apiJson<DocumentList>(`/v1/documents?limit=${DOCUMENT_PAGE_SIZE}&offset=0`);
}

/** Multipart upload. The browser sets the boundary, so no Content-Type header is passed. */
export async function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  const response = await apiFetch("/v1/documents", {
    method: "POST",
    body: form,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw await apiErrorFromResponse(response);
  return (await response.json()) as UploadResult;
}

export interface QueuedJob {
  document_id: string;
  job_id: string;
  status: string;
}

export function reindexDocument(documentId: string): Promise<QueuedJob> {
  return apiJson<QueuedJob>(`/v1/documents/${encodeURIComponent(documentId)}/reindex`, { method: "POST" });
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiJson<unknown>(`/v1/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
}

export function getIngestionJob(jobId: string): Promise<IngestionJob> {
  return apiJson<IngestionJob>(`/v1/ingestion-jobs/${encodeURIComponent(jobId)}`);
}
