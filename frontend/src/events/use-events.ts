import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { runEventStream } from "./event-stream";
import { invalidationsFor } from "./invalidation";

export type EventsStatus = "idle" | "connecting" | "connected" | "reconnecting";

/**
 * Keeps the TanStack Query cache fresh from the server's live-event stream while `enabled` (signed in).
 * Events say what changed; this hook marks the matching queries stale so mounted screens refetch. A `resync`
 * or a reconnect invalidates everything because the stream has no replay.
 */
export function useEvents(enabled: boolean): EventsStatus {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<EventsStatus>("idle");

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void runEventStream({
      signal: controller.signal,
      onStatus: setStatus,
      onReconnected: () => void queryClient.invalidateQueries(),
      onEvent: (event) => {
        const keys = invalidationsFor(event);
        if (keys === "all") {
          void queryClient.invalidateQueries();
          return;
        }
        for (const queryKey of keys) void queryClient.invalidateQueries({ queryKey });
      },
    });
    return () => {
      controller.abort();
      setStatus("idle");
    };
  }, [enabled, queryClient]);

  return enabled ? status : "idle";
}
