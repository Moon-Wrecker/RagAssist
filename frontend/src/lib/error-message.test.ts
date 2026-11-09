import { describe, expect, it } from "vitest";
import { ApiError, NetworkError } from "@/api/errors";
import { actionError } from "./error-message";

describe("actionError", () => {
  it("says the server could not be reached", () => {
    expect(actionError(new NetworkError(), "reply")).toMatch(/Can't reach the server/);
  });

  it("explains a role refusal and a missing resource", () => {
    expect(actionError(new ApiError(403, "Admin role required"), "upload documents")).toMatch(/not allowed to upload documents/);
    expect(actionError(new ApiError(404, "Document not found"), "delete it")).toMatch(/no longer exists/);
  });

  it("passes on the server's plain sentence for other client errors", () => {
    expect(actionError(new ApiError(409, "A workspace needs at least one active administrator."), "change that")).toBe(
      "A workspace needs at least one active administrator.",
    );
    expect(actionError(new ApiError(400, null), "send that")).toBe("Could not send that.");
  });

  it("does not leak server errors", () => {
    expect(actionError(new ApiError(500, "Traceback ..."), "do that")).toMatch(/Something went wrong/);
    expect(actionError("odd", "do that")).toMatch(/Something went wrong/);
  });
});
