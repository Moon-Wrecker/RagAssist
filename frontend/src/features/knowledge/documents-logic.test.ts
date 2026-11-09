import { describe, expect, it } from "vitest";
import { ApiError, NetworkError } from "@/api/errors";
import type { DocumentList, DocumentSummary, IngestionJob } from "@/api/documents";
import {
  describeUploadError,
  documentPhase,
  failureReason,
  isInFlight,
  jobStageLabel,
  phaseAnnouncement,
  statusLine,
  uploadReducer,
  withoutDocument,
  withRequeued,
  type UploadEntry,
} from "./documents-logic";

function doc(id: string, status: string, error: string | null = null): DocumentSummary {
  return {
    document_id: id,
    tenant_id: "t",
    filename: `${id}.pdf`,
    content_type: "application/pdf",
    file_size_bytes: 10,
    status,
    error_message: error,
    created_at: "2030-01-01T00:00:00Z",
    updated_at: "2030-01-01T00:00:00Z",
  };
}

function job(documentId: string, status: string, error: string | null = null): IngestionJob {
  return { job_id: "j", document_id: documentId, tenant_id: "t", status, attempts: 1, chunks_created: 0, tokens_indexed: 0, error_message: error, created_at: "2030-01-01T00:00:00Z" };
}

describe("phases", () => {
  it("groups the API statuses into four phases", () => {
    expect(documentPhase("queued")).toBe("queued");
    expect(documentPhase("pending")).toBe("queued");
    expect(documentPhase("processing")).toBe("working");
    expect(documentPhase("embedding")).toBe("working");
    expect(documentPhase("completed")).toBe("done");
    expect(documentPhase("failed")).toBe("failed");
  });

  it("knows which documents are still moving", () => {
    expect(isInFlight(doc("a", "queued"))).toBe(true);
    expect(isInFlight(doc("a", "processing"))).toBe(true);
    expect(isInFlight(doc("a", "completed"))).toBe(false);
    expect(isInFlight(doc("a", "failed"))).toBe(false);
  });
});

describe("status line and failure reason", () => {
  it("shows the job's stage while a document is in flight and the job belongs to it", () => {
    expect(statusLine(doc("a", "processing"), job("a", "embedding"))).toBe("Computing embeddings");
    expect(statusLine(doc("a", "processing"), job("other", "embedding"))).toBe("Indexing");
    expect(statusLine(doc("a", "processing"), undefined)).toBe("Indexing");
  });

  it("ignores a stale job once the document has settled", () => {
    expect(statusLine(doc("a", "completed"), job("a", "indexing"))).toBe("Ready");
    expect(statusLine(doc("a", "failed"), job("a", "indexing"))).toBe("Failed");
  });

  it("passes unknown job stages through", () => {
    expect(jobStageLabel("rerouting")).toBe("rerouting");
  });

  it("prefers the document's reason, then the job's, then a plain fallback", () => {
    expect(failureReason(doc("a", "failed", "Could not read the file."), job("a", "failed", "other"))).toBe("Could not read the file.");
    expect(failureReason(doc("a", "failed"), job("a", "failed", "Embedding service refused the request."))).toBe(
      "Embedding service refused the request.",
    );
    expect(failureReason(doc("a", "failed", "  "), undefined)).toMatch(/not recorded/);
  });
});

describe("optimistic list updates", () => {
  const list: DocumentList = { items: [doc("a", "completed"), doc("b", "failed", "Bad file")], total: 2 };

  it("removes one document and keeps the total honest", () => {
    const next = withoutDocument(list, "a");
    expect(next.items.map((d) => d.document_id)).toEqual(["b"]);
    expect(next.total).toBe(1);
    expect(list.items).toHaveLength(2);
    expect(withoutDocument(list, "missing").total).toBe(2);
  });

  it("puts a re-indexed document back in the queue and clears its failure", () => {
    const next = withRequeued(list, "b");
    expect(next.items[1]).toMatchObject({ status: "queued", error_message: null });
    expect(next.items[0]?.status).toBe("completed");
  });
});

describe("uploadReducer", () => {
  const entry = (id: string): UploadEntry => ({ id, name: `${id}.pdf`, size: 5, state: "uploading", message: null });

  it("tracks an upload from start to success", () => {
    let state = uploadReducer([], { type: "add", entry: entry("1") });
    state = uploadReducer(state, { type: "add", entry: entry("2") });
    state = uploadReducer(state, { type: "done", id: "1" });
    expect(state.map((e) => e.id)).toEqual(["2"]);
  });

  it("keeps a failure until it is dismissed", () => {
    let state = uploadReducer([], { type: "add", entry: entry("1") });
    state = uploadReducer(state, { type: "fail", id: "1", message: "Too big" });
    expect(state[0]).toMatchObject({ state: "failed", message: "Too big" });
    state = uploadReducer(state, { type: "dismiss", id: "1" });
    expect(state).toEqual([]);
  });

  it("clears everything", () => {
    expect(uploadReducer([entry("1"), entry("2")], { type: "clear" })).toEqual([]);
  });
});

describe("describeUploadError", () => {
  it("explains each refusal the API can give", () => {
    expect(describeUploadError(new ApiError(413, "x"), "big.pdf")).toMatch(/larger than the 50 MB limit/);
    expect(describeUploadError(new ApiError(415, "x"), "a.exe")).toMatch(/not a supported type/);
    expect(describeUploadError(new ApiError(403, "x"), "a.pdf")).toMatch(/Only workspace admins/);
    expect(describeUploadError(new ApiError(400, "x"), "a.pdf")).toMatch(/empty/);
  });

  it("handles a dropped connection and a server fault", () => {
    expect(describeUploadError(new NetworkError(), "a.pdf")).toMatch(/Check your connection/);
    expect(describeUploadError(new ApiError(500, "boom"), "a.pdf")).toMatch(/could not be uploaded/);
  });
});

describe("phaseAnnouncement", () => {
  it("announces nothing the first time it sees the documents", () => {
    const first = phaseAnnouncement({}, [doc("a", "processing"), doc("b", "completed")]);
    expect(first.message).toBeNull();
    expect(first.phases).toEqual({ a: "working", b: "done" });
  });

  it("announces a document that finishes or fails", () => {
    const before = { a: "working", b: "queued" } as const;
    expect(phaseAnnouncement(before, [doc("a", "completed"), doc("b", "queued")]).message).toBe("a.pdf is ready.");
    expect(phaseAnnouncement(before, [doc("a", "processing"), doc("b", "failed")]).message).toBe("b.pdf failed to index.");
  });

  it("does not announce moves between in-flight phases, or a new document", () => {
    const before = { a: "queued" } as const;
    expect(phaseAnnouncement(before, [doc("a", "processing"), doc("new", "queued")]).message).toBeNull();
  });
});
