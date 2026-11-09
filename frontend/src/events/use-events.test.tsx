import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/api/query-keys";
import { setAccessToken } from "@/api/token-store";
import { fakeToken, frame, mockFetch, sseResponse } from "@/test/helpers";
import { useEvents } from "./use-events";

beforeEach(() => setAccessToken(fakeToken("access")));
afterEach(() => setAccessToken(null));

function setup(enabled: boolean) {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useEvents(enabled), { wrapper });
  return { invalidate, ...hook };
}

describe("useEvents", () => {
  it("invalidates the queries named by each event", async () => {
    mockFetch({
      "GET /v1/events": () =>
        sseResponse(
          [frame("ready"), frame("message.created", { conversation_id: "c1" }), frame("document.changed", { document_id: "d1" })],
          { hold: true },
        ),
    });
    const { invalidate, result } = setup(true);
    await waitFor(() => expect(result.current).toBe("connected"));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.conversation("c1") }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.documents });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.escalations });
  });

  it("invalidates everything on resync", async () => {
    mockFetch({ "GET /v1/events": () => sseResponse([frame("ready"), frame("resync")], { hold: true }) });
    const { invalidate } = setup(true);
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith());
  });

  it("does not connect while disabled", () => {
    const fetchMock = mockFetch({});
    const { result } = setup(false);
    expect(result.current).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("closes the stream on unmount", async () => {
    let signal: AbortSignal | null | undefined;
    mockFetch({
      "GET /v1/events": ({ init }) => {
        signal = init.signal;
        return sseResponse([frame("ready")], { hold: true });
      },
    });
    const { result, unmount } = setup(true);
    await waitFor(() => expect(result.current).toBe("connected"));
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
