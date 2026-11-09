import { ApiError, NetworkError } from "@/api/errors";

const UNREACHABLE = "Can't reach the server. Check your connection and try again.";
const GENERIC = "Something went wrong on our side. Try again in a moment.";

function waitText(error: ApiError): string {
  if (!error.retryAfter) return "a few minutes";
  const minutes = Math.ceil(error.retryAfter / 60);
  return minutes <= 1 ? "a minute" : `${minutes} minutes`;
}

/** Plain-language reason a sign-in failed. The server's 401 is deliberately generic, so this one is too. */
export function signInMessage(error: unknown): string {
  if (error instanceof NetworkError) return UNREACHABLE;
  if (error instanceof ApiError) {
    if (error.status === 401) return "That workspace, email or password is not right. Check each one and try again.";
    if (error.status === 429) return `Too many attempts. Wait ${waitText(error)} and try again.`;
    if (error.status === 422) return "Fill in the workspace, email and password.";
  }
  return GENERIC;
}

/** Plain-language reason spending an invite or reset link failed. */
export function acceptLinkMessage(error: unknown): string {
  if (error instanceof NetworkError) return UNREACHABLE;
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "This link is not valid. It may have been used already or it has expired. Ask a workspace admin for a new one.";
    }
    if (error.status === 422) return error.detail ?? "That password was not accepted. Choose a longer one.";
    if (error.status === 429) return `Too many attempts. Wait ${waitText(error)} and try again.`;
  }
  return GENERIC;
}
