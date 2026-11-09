import { randomUUID } from "node:crypto";
import type { Page, Route } from "@playwright/test";

export type Role = "user" | "agent" | "admin";

/** Runtime-generated, obviously fake credentials; nothing credential-shaped is written in the specs. */
export function fakeCredentials() {
  return {
    workspace: "example",
    email: `person-${randomUUID().slice(0, 8)}@example.test`,
    password: `pw-${randomUUID()}`,
  };
}

export interface MockOptions {
  role?: Role;
  /** Start with a valid refresh cookie, so the app restores the session on load. */
  signedIn?: boolean;
  /** What POST /v1/auth/login answers: ok, or a status such as 401 or 429. */
  loginStatus?: number;
  /** What POST /v1/auth/invites/accept answers. */
  acceptStatus?: number;
}

export interface MockApi {
  requests: { method: string; path: string; body: unknown }[];
  /** The parsed JSON body of the last request to this path, if any. */
  lastBody: (path: string) => unknown;
}

function sessionBody(role: Role, email: string) {
  return {
    access_token: `test-access-${randomUUID()}`,
    token_type: "bearer",
    expires_in: 900,
    user: { id: randomUUID(), email, role, status: "active" },
    workspace: { id: randomUUID(), name: "Example Workspace", slug: "example" },
  };
}

const json = (route: Route, status: number, body: unknown, headers: Record<string, string> = {}) =>
  route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });

/** Intercept every /v1 call in the browser. No backend is involved. */
export async function mockApi(page: Page, options: MockOptions = {}): Promise<MockApi> {
  const { role = "user", loginStatus = 200, acceptStatus = 200 } = options;
  let signedIn = options.signedIn ?? false;
  const email = fakeCredentials().email;
  const log: MockApi["requests"] = [];

  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const body = ((): unknown => {
      try {
        return request.postDataJSON();
      } catch {
        return null;
      }
    })();
    log.push({ method: request.method(), path, body });

    switch (`${request.method()} ${path}`) {
      case "POST /v1/auth/refresh":
        return signedIn ? json(route, 200, sessionBody(role, email)) : json(route, 401, { detail: "No session." });
      case "POST /v1/auth/login":
        if (loginStatus === 200) {
          signedIn = true;
          return json(route, 200, sessionBody(role, email));
        }
        return json(route, loginStatus, { detail: "Invalid workspace, email or password." }, loginStatus === 429 ? { "Retry-After": "120" } : {});
      case "POST /v1/auth/invites/accept":
        if (acceptStatus === 200) {
          signedIn = true;
          return json(route, 200, sessionBody(role, email));
        }
        return json(route, acceptStatus, { detail: acceptStatus === 422 ? "Password must be at least 12 characters." : "Invalid link." });
      case "POST /v1/auth/logout":
        signedIn = false;
        return route.fulfill({ status: 204 });
      case "GET /v1/events":
        // One ready frame, then the stream ends; the client reconnects with backoff.
        return route.fulfill({ status: 200, contentType: "text/event-stream", body: "event: ready\ndata: {}\n\n" });
      default:
        return json(route, 404, { detail: "Not mocked." });
    }
  });

  return {
    requests: log,
    lastBody: (path) => [...log].reverse().find((entry) => entry.path === path)?.body,
  };
}
