import { ApiError, NetworkError } from "@/api/errors";

const UNREACHABLE = "Can't reach the server. Check your connection and try again.";
const GENERIC = "Something went wrong on our side. Try again in a moment.";

/**
 * One plain sentence for a failed action. The server's own message is used for 4xx answers (it is written for
 * people: "A workspace needs at least one active administrator."), except a few statuses where we say more.
 * `what` completes "Could not ...", for example "change that role".
 */
export function actionError(error: unknown, what: string): string {
  if (error instanceof NetworkError) return UNREACHABLE;
  if (error instanceof ApiError) {
    if (error.status === 403) return `Your role is not allowed to ${what}. Ask a workspace admin.`;
    if (error.status === 404) return `Could not ${what}: it no longer exists. The list has been refreshed.`;
    if (error.status === 429) return "Too many requests. Wait a moment and try again.";
    if (error.status >= 400 && error.status < 500 && error.detail) return error.detail;
    if (error.status < 500) return `Could not ${what}.`;
  }
  return GENERIC;
}
