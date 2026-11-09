import { describe, expect, it } from "vitest";
import { formatBytes, timeAgo, timeUntil } from "./format";

describe("formatBytes", () => {
  it("uses binary units with plain labels", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(50 * 1024 * 1024)).toBe("50 MB");
    expect(formatBytes(2.25 * 1024 * 1024 * 1024)).toBe("2.3 GB");
  });
  it("copes with nonsense", () => {
    expect(formatBytes(-1)).toBe("0 B");
    expect(formatBytes(Number.NaN)).toBe("0 B");
  });
});

describe("relative times", () => {
  const now = new Date("2030-01-10T12:00:00Z");
  it("says how long ago", () => {
    expect(timeAgo("2030-01-10T11:59:40Z", now)).toBe("just now");
    expect(timeAgo("2030-01-10T11:59:00Z", now)).toBe("1 minute ago");
    expect(timeAgo("2030-01-10T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2030-01-08T12:00:00Z", now)).toBe("2 days ago");
    expect(timeAgo("not a date", now)).toBe("");
  });
  it("says how long until", () => {
    expect(timeUntil("2030-01-13T12:00:00Z", now)).toBe("in 3 days");
    expect(timeUntil("2030-01-10T17:00:00Z", now)).toBe("in 5 hours");
    expect(timeUntil("2030-01-10T12:20:00Z", now)).toBe("in 20 minutes");
    expect(timeUntil("2030-01-10T11:00:00Z", now)).toBe("expired");
  });
});
