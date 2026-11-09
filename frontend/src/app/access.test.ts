import { describe, expect, it } from "vitest";
import { canAccess, landingPath, routesFor } from "./access";

describe("role access", () => {
  it("gives a customer only Chat", () => {
    expect(routesFor("user").map((r) => r.label)).toEqual(["Chat"]);
  });
  it("adds Inbox for agents", () => {
    expect(routesFor("agent").map((r) => r.label)).toEqual(["Chat", "Inbox"]);
  });
  it("adds Knowledge and Team for admins", () => {
    expect(routesFor("admin").map((r) => r.label)).toEqual(["Chat", "Inbox", "Knowledge", "Team"]);
  });
  it("refuses unlisted paths and roles", () => {
    expect(canAccess("user", "/inbox")).toBe(false);
    expect(canAccess("agent", "/team")).toBe(false);
    expect(canAccess("admin", "/team")).toBe(true);
    expect(canAccess("admin", "/nowhere")).toBe(false);
  });
  it("lands on the requested page only when the role may open it", () => {
    expect(landingPath("admin", "/team")).toBe("/team");
    expect(landingPath("user", "/team")).toBe("/");
    expect(landingPath("user", undefined)).toBe("/");
  });
});
