import { randomUUID } from "node:crypto";
import type { Page, Route } from "@playwright/test";
import { mockApi, type Role } from "./mock-api";

/**
 * A small stateful fake of the inbox, knowledge-base and team endpoints, layered on top of `mockApi` (which answers
 * sign-in and the event stream). Playwright runs the most recently registered route first, and anything this does
 * not handle falls back to `mockApi`. No backend runs and every value is an obvious placeholder.
 *
 * Live events: the mocked event stream closes after each response, so frames queued with `pushEvent` are delivered
 * on the next (re)connection, a second or so later. State changes made through the helpers take effect at once.
 */

export interface MockEscalation {
  id: string;
  title: string;
  status: "escalated" | "resolved";
  priority: string;
  updatedAt: string;
  messages: { role: string; text: string; created_at: string }[];
}

export interface MockDocument {
  id: string;
  filename: string;
  contentType: string;
  size: number;
  status: string;
  error: string | null;
  createdAt: string;
}

export interface MockJob {
  id: string;
  documentId: string;
  status: string;
  error: string | null;
}

export interface MockMember {
  id: string;
  email: string;
  role: string;
  status: string;
  has_password: boolean;
}

export interface MockInvite {
  id: string;
  kind: string;
  email: string;
  role: string;
  expiresAt: string;
  createdAt: string;
}

export interface AdminSeed {
  role?: Role;
  escalations?: MockEscalation[];
  documents?: MockDocument[];
  members?: MockMember[];
  invites?: MockInvite[];
}

export const FAKE_LINK_PREFIX = "https://app.example.invalid/accept#token=placeholder-not-a-real-link-";

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString();

export function escalation(overrides: Partial<MockEscalation> & { title: string }): MockEscalation {
  return {
    id: randomUUID(),
    status: "escalated",
    priority: "high",
    updatedAt: minutesAgo(12),
    messages: [
      { role: "user", text: "Hello, I need help with this.", created_at: minutesAgo(15) },
      { role: "assistant", text: "I could not find an answer in the documents, so I have asked a colleague to help.", created_at: minutesAgo(14) },
    ],
    ...overrides,
  };
}

export function documentRow(overrides: Partial<MockDocument> & { filename: string }): MockDocument {
  return {
    id: randomUUID(),
    contentType: "application/pdf",
    size: 482_000,
    status: "completed",
    error: null,
    createdAt: minutesAgo(180),
    ...overrides,
  };
}

export function member(email: string, role: string, overrides: Partial<MockMember> = {}): MockMember {
  return { id: randomUUID(), email, role, status: "active", has_password: true, ...overrides };
}

export function invite(email: string, role: string, kind = "invite"): MockInvite {
  return { id: randomUUID(), kind, email, role, expiresAt: hoursFromNow(70), createdAt: minutesAgo(30) };
}

export interface AdminMock {
  /** Every request the fake handled, in order. */
  calls: { method: string; path: string; body: unknown }[];
  escalations: MockEscalation[];
  documents: MockDocument[];
  jobs: MockJob[];
  members: MockMember[];
  invites: MockInvite[];
  selfId: string;
  selfEmail: string;
  /** Queue an event frame for the next stream connection. */
  pushEvent: (type: string, data?: Record<string, unknown>) => void;
  /** A customer writes in an escalated thread; agents are told through the live stream. */
  customerSays: (conversationId: string, text: string) => void;
  /** Move an ingestion job to a stage (or to failed with a reason) and tell admins through the live stream. */
  advanceJob: (jobId: string, status: string, error?: string) => void;
  /** Make the next request that matches `METHOD /path` answer with this status and detail. */
  failNext: (key: string, status: number, detail: string) => void;
  lastJobId: () => string;
}

const json = (route: Route, status: number, body: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

export async function mockAdminApi(page: Page, seed: AdminSeed = {}): Promise<AdminMock> {
  const role = seed.role ?? "admin";
  await mockApi(page, { role, signedIn: true });

  const selfId = randomUUID();
  const selfEmail = `me-${randomUUID().slice(0, 6)}@example.test`;
  const mock: AdminMock = {
    calls: [],
    escalations: seed.escalations ?? [],
    documents: seed.documents ?? [],
    jobs: [],
    members: seed.members ?? [],
    invites: seed.invites ?? [],
    selfId,
    selfEmail,
    pushEvent: (type, data = {}) => frames.push(`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`),
    customerSays: (conversationId, text) => {
      const thread = mock.escalations.find((item) => item.id === conversationId);
      if (!thread) throw new Error("no such conversation in the fake");
      thread.messages.push({ role: "user", text, created_at: new Date().toISOString() });
      thread.updatedAt = new Date().toISOString();
      mock.pushEvent("message.created", { conversation_id: conversationId });
      mock.pushEvent("escalation.changed", { conversation_id: conversationId });
    },
    advanceJob: (jobId, status, error) => {
      const job = mock.jobs.find((candidate) => candidate.id === jobId);
      if (!job) throw new Error("no such job in the fake");
      job.status = status;
      job.error = error ?? null;
      const doc = mock.documents.find((candidate) => candidate.id === job.documentId);
      if (doc) {
        doc.status = status === "completed" ? "completed" : status === "failed" ? "failed" : status === "queued" ? "queued" : "processing";
        doc.error = status === "failed" ? (error ?? null) : null;
      }
      mock.pushEvent("job.updated", { job_id: job.id, document_id: job.documentId });
      mock.pushEvent("document.changed", { document_id: job.documentId });
    },
    failNext: (key, status, detail) => failures.set(key, { status, detail }),
    lastJobId: () => mock.jobs[mock.jobs.length - 1]?.id ?? "",
  };
  const frames: string[] = [];
  const failures = new Map<string, { status: number; detail: string }>();

  const summary = (item: MockEscalation) => ({
    escalation_id: item.id,
    tenant_id: "tenant-placeholder",
    status: item.status,
    summary: item.title,
    priority: item.priority,
    created_at: item.messages[0]?.created_at ?? item.updatedAt,
    updated_at: item.updatedAt,
  });
  const detail = (item: MockEscalation) => ({
    conversation_id: item.id,
    tenant_id: "tenant-placeholder",
    title: item.title,
    status: item.status,
    messages: item.messages,
    created_at: item.messages[0]?.created_at ?? item.updatedAt,
    updated_at: item.updatedAt,
  });
  const documentOut = (doc: MockDocument) => ({
    document_id: doc.id,
    tenant_id: "tenant-placeholder",
    filename: doc.filename,
    content_type: doc.contentType,
    file_size_bytes: doc.size,
    status: doc.status,
    error_message: doc.error,
    created_at: doc.createdAt,
    updated_at: doc.createdAt,
  });
  const jobOut = (job: MockJob) => ({
    job_id: job.id,
    document_id: job.documentId,
    tenant_id: "tenant-placeholder",
    status: job.status,
    attempts: 1,
    chunks_created: 0,
    tokens_indexed: 0,
    error_message: job.error,
    created_at: minutesAgo(1),
  });
  const inviteOut = (item: MockInvite) => ({
    id: item.id,
    kind: item.kind,
    email: item.email,
    role: item.role,
    expires_at: item.expiresAt,
    created_at: item.createdAt,
  });
  const issued = (item: MockInvite) => ({
    invite_id: item.id,
    kind: item.kind,
    email: item.email,
    role: item.role,
    url: `${FAKE_LINK_PREFIX}${randomUUID()}`,
    expires_at: item.expiresAt,
  });

  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const key = `${request.method()} ${path}`;
    const body = ((): unknown => {
      try {
        return request.postDataJSON();
      } catch {
        return null;
      }
    })();
    const log = () => mock.calls.push({ method: request.method(), path, body });

    if (key === "POST /v1/auth/refresh") {
      // A stable user id, so the Team screen can tell which row is the signed-in admin.
      return json(route, 200, {
        access_token: `test-access-${randomUUID()}`,
        token_type: "bearer",
        expires_in: 900,
        user: { id: selfId, email: selfEmail, role, status: "active" },
        workspace: { id: randomUUID(), name: "Example Workspace", slug: "example" },
      });
    }
    if (key === "GET /v1/events") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: ready\ndata: {}\n\n${frames.splice(0).join("")}`,
      });
    }

    const failure = failures.get(key);
    if (failure) {
      failures.delete(key);
      log();
      return json(route, failure.status, { detail: failure.detail });
    }

    let match: RegExpMatchArray | null;

    // --- inbox ---
    if (key === "GET /v1/escalations") return json(route, 200, { items: mock.escalations.map(summary), total: mock.escalations.length });
    if ((match = path.match(/^\/v1\/conversations\/([^/]+)$/)) && request.method() === "GET") {
      const item = mock.escalations.find((candidate) => candidate.id === match![1]);
      return item ? json(route, 200, detail(item)) : json(route, 404, { detail: "Conversation not found" });
    }
    if ((match = path.match(/^\/v1\/escalations\/([^/]+)\/(reply|resolve)$/)) && request.method() === "POST") {
      log();
      const item = mock.escalations.find((candidate) => candidate.id === match![1]);
      if (!item) return json(route, 404, { detail: "Escalation not found" });
      if (item.status !== "escalated") return json(route, 409, { detail: "This conversation is not escalated." });
      if (match[2] === "reply") {
        const text = String((body as { text?: string } | null)?.text ?? "");
        const reply = { role: "agent", text, created_at: new Date().toISOString() };
        item.messages.push(reply);
        item.updatedAt = reply.created_at;
        return json(route, 200, { ...reply, user_id: selfId });
      }
      item.status = "resolved";
      item.updatedAt = new Date().toISOString();
      return json(route, 200, { escalation_id: item.id, status: "resolved", resolved_at: item.updatedAt });
    }

    // --- knowledge ---
    if (key === "GET /v1/documents") return json(route, 200, { items: mock.documents.map(documentOut), total: mock.documents.length });
    if (key === "POST /v1/documents") {
      log();
      const raw = request.postDataBuffer()?.toString("latin1") ?? "";
      const filename = raw.match(/filename="([^"]*)"/)?.[1] ?? "unnamed";
      const contentType = raw.match(/Content-Type:\s*([^\r\n]+)/i)?.[1] ?? "";
      const doc = documentRow({ filename, contentType, status: "queued", size: 1024, createdAt: new Date().toISOString() });
      const job: MockJob = { id: randomUUID(), documentId: doc.id, status: "queued", error: null };
      mock.documents.unshift(doc);
      mock.jobs.push(job);
      mock.pushEvent("job.updated", { job_id: job.id, document_id: doc.id });
      mock.pushEvent("document.changed", { document_id: doc.id });
      return json(route, 202, { document_id: doc.id, job_id: job.id, object_key: "placeholder/key", status: "queued" });
    }
    if ((match = path.match(/^\/v1\/ingestion-jobs\/([^/]+)$/))) {
      const job = mock.jobs.find((candidate) => candidate.id === match![1]);
      return job ? json(route, 200, jobOut(job)) : json(route, 404, { detail: "Ingestion job not found" });
    }
    if ((match = path.match(/^\/v1\/documents\/([^/]+)\/reindex$/)) && request.method() === "POST") {
      log();
      const doc = mock.documents.find((candidate) => candidate.id === match![1]);
      if (!doc) return json(route, 404, { detail: "Document not found" });
      const job: MockJob = { id: randomUUID(), documentId: doc.id, status: "queued", error: null };
      mock.jobs.push(job);
      doc.status = "queued";
      doc.error = null;
      return json(route, 200, { document_id: doc.id, job_id: job.id, status: "queued" });
    }
    if ((match = path.match(/^\/v1\/documents\/([^/]+)$/)) && request.method() === "DELETE") {
      log();
      const index = mock.documents.findIndex((candidate) => candidate.id === match![1]);
      if (index === -1) return json(route, 404, { detail: "Document not found" });
      mock.documents.splice(index, 1);
      return json(route, 200, { deleted: true, document_id: match[1] });
    }

    // --- team ---
    if (key === "GET /v1/team/members") return json(route, 200, mock.members);
    if ((match = path.match(/^\/v1\/team\/members\/([^/]+)$/)) && request.method() === "PATCH") {
      log();
      const target = mock.members.find((candidate) => candidate.id === match![1]);
      if (!target) return json(route, 404, { detail: "No such member." });
      const patch = (body ?? {}) as { role?: string | null; status?: string | null };
      if (patch.role) target.role = patch.role;
      if (patch.status) target.status = patch.status;
      return json(route, 200, target);
    }
    if ((match = path.match(/^\/v1\/team\/members\/([^/]+)\/reset-link$/)) && request.method() === "POST") {
      log();
      const target = mock.members.find((candidate) => candidate.id === match![1]);
      if (!target) return json(route, 404, { detail: "No such member." });
      const item = invite(target.email, target.role, "reset");
      mock.invites.push(item);
      return json(route, 201, issued(item));
    }
    if (key === "GET /v1/team/invites") return json(route, 200, mock.invites.map(inviteOut));
    if (key === "POST /v1/team/invites") {
      log();
      const request_ = (body ?? {}) as { email?: string; role?: string };
      if (mock.members.some((candidate) => candidate.email === request_.email)) {
        return json(route, 409, { detail: "That address already has an account in this workspace." });
      }
      const item = invite(request_.email ?? "", request_.role ?? "user");
      mock.invites.push(item);
      return json(route, 201, issued(item));
    }
    if ((match = path.match(/^\/v1\/team\/invites\/([^/]+)$/)) && request.method() === "DELETE") {
      log();
      const index = mock.invites.findIndex((candidate) => candidate.id === match![1]);
      if (index === -1) return json(route, 404, { detail: "No such pending invite." });
      mock.invites.splice(index, 1);
      return route.fulfill({ status: 204 });
    }

    return route.fallback();
  });

  return mock;
}
