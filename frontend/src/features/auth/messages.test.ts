import { describe, expect, it } from "vitest";
import { ApiError, NetworkError } from "@/api/errors";
import { acceptLinkMessage, signInMessage } from "./messages";

describe("signInMessage", () => {
  it("is generic for 401 so it never says which field was wrong", () => {
    const text = signInMessage(new ApiError(401, "Invalid workspace, email or password."));
    expect(text).toMatch(/workspace, email or password/i);
  });
  it("tells the person how long to wait on 429", () => {
    expect(signInMessage(new ApiError(429, null, 120))).toContain("2 minutes");
    expect(signInMessage(new ApiError(429, null, 30))).toContain("a minute");
    expect(signInMessage(new ApiError(429, null))).toContain("a few minutes");
  });
  it("distinguishes an unreachable server", () => {
    expect(signInMessage(new NetworkError())).toMatch(/reach the server/i);
  });
  it("falls back for anything else", () => {
    expect(signInMessage(new ApiError(500, null))).toMatch(/something went wrong/i);
    expect(signInMessage(new Error("x"))).toMatch(/something went wrong/i);
  });
});

describe("acceptLinkMessage", () => {
  it("explains an invalid, used or expired link and what to do", () => {
    expect(acceptLinkMessage(new ApiError(401, null))).toMatch(/ask a workspace admin/i);
  });
  it("shows the server's password rule on 422", () => {
    expect(acceptLinkMessage(new ApiError(422, "Password must be at least 12 characters."))).toBe(
      "Password must be at least 12 characters.",
    );
  });
});
