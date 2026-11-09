/** An HTTP failure from the API. `detail` is the server's plain message when it sent one. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  readonly retryAfter: number | null;

  constructor(status: number, detail: string | null, retryAfter: number | null = null) {
    super(detail ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

/** The server could not be reached at all (offline, proxy down, DNS). */
export class NetworkError extends Error {
  constructor(options?: { cause?: unknown }) {
    super("The server could not be reached.", options);
    this.name = "NetworkError";
  }
}

/**
 * FastAPI answers `{"detail": "text"}` for application errors and `{"detail": [{"msg": ...}]}` for request
 * validation. Both reduce to one readable sentence, or null when the body is not JSON.
 */
export function detailFromBody(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        typeof item === "object" && item !== null && "msg" in item ? String((item as { msg: unknown }).msg) : null,
      )
      .filter((m): m is string => m !== null);
    return messages.length > 0 ? messages.join(" ") : null;
  }
  return null;
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const detail = await response.json().then(detailFromBody, () => null);
  const retry = Number(response.headers.get("Retry-After"));
  return new ApiError(response.status, detail, Number.isFinite(retry) && retry > 0 ? retry : null);
}
