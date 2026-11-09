import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { optimisticTarget, useOptimisticMutation } from "./optimistic";

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

const LIST = ["list"] as const;
const DETAIL = ["detail", "1"] as const;

describe("useOptimisticMutation", () => {
  it("shows the change at once and keeps it when the server agrees", async () => {
    const { queryClient, wrapper } = setup();
    queryClient.setQueryData(LIST, ["a"]);
    queryClient.setQueryData(DETAIL, { n: 0 });
    let release: () => void = () => {};
    const mutationFn = vi.fn(() => new Promise<string>((resolve) => (release = () => resolve("ok"))));

    const { result } = renderHook(
      () =>
        useOptimisticMutation<string, string>({
          mutationFn,
          targets: [
            optimisticTarget<string[], string>(LIST, (cache, item) => [...cache, item]),
            optimisticTarget<{ n: number }, string>(DETAIL, (cache) => ({ n: cache.n + 1 })),
          ],
        }),
      { wrapper },
    );

    act(() => result.current.mutate("b"));
    await waitFor(() => expect(queryClient.getQueryData(LIST)).toEqual(["a", "b"]));
    expect(queryClient.getQueryData(DETAIL)).toEqual({ n: 1 });

    release();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(LIST)).toEqual(["a", "b"]);
  });

  it("puts every touched query back when the server refuses, and reports the error", async () => {
    const { queryClient, wrapper } = setup();
    queryClient.setQueryData(LIST, ["a"]);
    queryClient.setQueryData(DETAIL, { n: 0 });
    const onError = vi.fn();

    const { result } = renderHook(
      () =>
        useOptimisticMutation<string, string>({
          mutationFn: () => Promise.reject(new Error("refused")),
          onError,
          targets: [
            optimisticTarget<string[], string>(LIST, (cache, item) => [...cache, item]),
            optimisticTarget<{ n: number }, string>(DETAIL, (cache) => ({ n: cache.n + 1 })),
          ],
        }),
      { wrapper },
    );

    act(() => result.current.mutate("b"));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(queryClient.getQueryData(LIST)).toEqual(["a"]);
    expect(queryClient.getQueryData(DETAIL)).toEqual({ n: 0 });
    expect(onError).toHaveBeenCalledOnce();
  });

  it("skips a query that has not been loaded and still calls the server", async () => {
    const { queryClient, wrapper } = setup();
    const mutationFn = vi.fn(async () => "ok");
    const { result } = renderHook(
      () =>
        useOptimisticMutation<string, string>({
          mutationFn,
          targets: [optimisticTarget<string[], string>(LIST, (cache, item) => [...cache, item])],
        }),
      { wrapper },
    );
    act(() => result.current.mutate("b"));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mutationFn).toHaveBeenCalledOnce();
    expect(queryClient.getQueryData(LIST)).toBeUndefined();
  });
});
