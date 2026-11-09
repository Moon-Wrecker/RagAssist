import { afterEach, describe, expect, it } from "vitest";
import { captureFragmentToken, clearCapturedToken, parseFragmentToken } from "./fragment-token";

afterEach(() => {
  clearCapturedToken();
  window.history.replaceState(null, "", "/");
});

describe("parseFragmentToken", () => {
  it("reads the token from a fragment", () => {
    expect(parseFragmentToken("#token=abc.def")).toBe("abc.def");
  });
  it("accepts a fragment without the leading hash", () => {
    expect(parseFragmentToken("token=abc")).toBe("abc");
  });
  it("returns null when there is no token or it is blank", () => {
    expect(parseFragmentToken("")).toBeNull();
    expect(parseFragmentToken("#other=1")).toBeNull();
    expect(parseFragmentToken("#token=")).toBeNull();
    expect(parseFragmentToken("#token=%20")).toBeNull();
  });
});

describe("captureFragmentToken", () => {
  it("returns the token and removes the fragment from the address and history entry", () => {
    window.history.replaceState({ idx: 3 }, "", "/accept?x=1#token=secret-value");
    expect(captureFragmentToken()).toBe("secret-value");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname + window.location.search).toBe("/accept?x=1");
    expect(window.location.href).not.toContain("secret-value");
    expect(window.history.state).toEqual({ idx: 3 });
  });

  it("is idempotent, so a second render (StrictMode) still finds the token", () => {
    window.history.replaceState(null, "", "/accept#token=again");
    expect(captureFragmentToken()).toBe("again");
    expect(captureFragmentToken()).toBe("again");
  });

  it("returns null when the link has no token", () => {
    window.history.replaceState(null, "", "/accept");
    expect(captureFragmentToken()).toBeNull();
  });

  it("forgets the token once cleared", () => {
    window.history.replaceState(null, "", "/accept#token=gone");
    captureFragmentToken();
    clearCapturedToken();
    expect(captureFragmentToken()).toBeNull();
  });
});
