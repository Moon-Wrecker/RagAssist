import { appendFileSync } from "node:fs";
import { it } from "vitest";
import { frame, mockFetch, sseResponse } from "@/test/helpers";
import { runEventStream } from "./event-stream";

const L = (...a: unknown[]) =>
  appendFileSync("C:/Users/ASUS/.claude/jobs/b3bbb739/tmp/dbg2.log", a.map((x) => JSON.stringify(x)).join(" ") + "\n");

it("dbg", async () => {
  const c = new AbortController();
  const m = mockFetch({
    "GET /v1/events": () => {
      setTimeout(() => c.abort(), 30);
      return sseResponse([frame("ready"), frame("reauth")], { hold: true });
    },
  });
  const ev: string[] = [];
  await runEventStream({
    signal: c.signal,
    onEvent: (e) => ev.push(e.type),
    onReconnected: () => {},
    onStatus: (s) => L("ST", s),
    random: () => 0,
    sleep: async (ms) => {
      L("SLEEP", ms);
      await new Promise((r) => setTimeout(r, 5));
    },
  });
  L("EV", ev, m.mock.calls.length);
});
