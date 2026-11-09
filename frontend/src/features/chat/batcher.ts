/**
 * Collects streamed text and hands it over at most once per animation frame, so a fast stream of small tokens
 * causes one React update per frame instead of one per token. `schedule` and `cancel` are replaceable so the
 * logic is testable without a browser; by default they are `requestAnimationFrame` and `cancelAnimationFrame`.
 */
export interface FrameBatcher {
  push: (text: string) => void;
  /** Hand over anything pending right now (before a state change that must see all text, such as `done`). */
  flush: () => void;
  /** Drop anything pending and any scheduled frame (reset, stop, unmount). */
  discard: () => void;
}

export interface BatcherScheduler {
  schedule: (callback: () => void) => number;
  cancel: (handle: number) => void;
}

const browserScheduler: BatcherScheduler = {
  schedule: (callback) => requestAnimationFrame(() => callback()),
  cancel: (handle) => cancelAnimationFrame(handle),
};

export function createFrameBatcher(onFlush: (text: string) => void, scheduler: BatcherScheduler = browserScheduler): FrameBatcher {
  let pending = "";
  let handle: number | null = null;

  function emit() {
    handle = null;
    if (pending === "") return;
    const text = pending;
    pending = "";
    onFlush(text);
  }

  return {
    push(text) {
      pending += text;
      if (handle === null) handle = scheduler.schedule(emit);
    },
    flush() {
      if (handle !== null) {
        scheduler.cancel(handle);
        handle = null;
      }
      emit();
    },
    discard() {
      if (handle !== null) {
        scheduler.cancel(handle);
        handle = null;
      }
      pending = "";
    },
  };
}
