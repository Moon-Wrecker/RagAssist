import { describe, expect, it } from "vitest";
import { createFrameBatcher, type BatcherScheduler } from "./batcher";

function fakeFrames() {
  const queue = new Map<number, () => void>();
  let next = 1;
  const scheduler: BatcherScheduler = {
    schedule: (callback) => {
      queue.set(next, callback);
      return next++;
    },
    cancel: (handle) => void queue.delete(handle),
  };
  return {
    scheduler,
    pending: () => queue.size,
    /** Run the frame callbacks that are due, as the browser would before the next paint. */
    frame: () => {
      const due = [...queue.values()];
      queue.clear();
      for (const callback of due) callback();
    },
  };
}

describe("createFrameBatcher", () => {
  it("hands over many tokens as one update per frame", () => {
    const frames = fakeFrames();
    const flushed: string[] = [];
    const batcher = createFrameBatcher((text) => flushed.push(text), frames.scheduler);
    for (const token of ["Ref", "unds ", "take ", "5 days"]) batcher.push(token);
    expect(flushed).toEqual([]);
    expect(frames.pending()).toBe(1);
    frames.frame();
    expect(flushed).toEqual(["Refunds take 5 days"]);
    batcher.push("!");
    frames.frame();
    expect(flushed).toEqual(["Refunds take 5 days", "!"]);
  });

  it("flush delivers pending text at once and cancels the scheduled frame", () => {
    const frames = fakeFrames();
    const flushed: string[] = [];
    const batcher = createFrameBatcher((text) => flushed.push(text), frames.scheduler);
    batcher.push("abc");
    batcher.flush();
    expect(flushed).toEqual(["abc"]);
    expect(frames.pending()).toBe(0);
    batcher.flush();
    expect(flushed).toEqual(["abc"]);
  });

  it("discard drops pending text, as a reset of the answer must", () => {
    const frames = fakeFrames();
    const flushed: string[] = [];
    const batcher = createFrameBatcher((text) => flushed.push(text), frames.scheduler);
    batcher.push("partial answer");
    batcher.discard();
    frames.frame();
    expect(flushed).toEqual([]);
    batcher.push("fresh");
    frames.frame();
    expect(flushed).toEqual(["fresh"]);
  });
});
