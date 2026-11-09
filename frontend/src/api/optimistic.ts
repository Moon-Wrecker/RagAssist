import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";

/** One cached query that a change updates ahead of the server's answer. */
export interface OptimisticTarget<TVars> {
  queryKey: QueryKey;
  update: (cache: unknown, vars: TVars) => unknown;
}

/** Type-safe way to build a target: `apply` receives the cache typed as the query's data. */
export function optimisticTarget<TCache, TVars>(
  queryKey: QueryKey,
  apply: (cache: TCache, vars: TVars) => TCache,
): OptimisticTarget<TVars> {
  return { queryKey, update: (cache, vars) => apply(cache as TCache, vars) };
}

/**
 * A mutation that updates the cached lists and details at once and puts them back if the server refuses.
 *
 * Order matters: in-flight refetches are cancelled first (otherwise a stale response lands on top of the optimistic
 * value), the previous values are kept for the rollback, and every touched query is invalidated when the call
 * settles so the screen ends up showing what the server says, not what we guessed. A target whose query has not
 * been loaded is skipped, because there is nothing to update.
 */
export function useOptimisticMutation<TVars, TData>({
  targets,
  mutationFn,
  invalidate = [],
  onSuccess,
  onError,
}: {
  targets: OptimisticTarget<TVars>[];
  mutationFn: (vars: TVars) => Promise<TData>;
  /** More keys to refetch when the call settles. */
  invalidate?: QueryKey[];
  onSuccess?: (data: TData, vars: TVars) => void;
  onError?: (error: unknown, vars: TVars) => void;
}) {
  const queryClient = useQueryClient();
  return useMutation<TData, unknown, TVars, { previous: { queryKey: QueryKey; data: unknown }[] }>({
    mutationFn,
    onMutate: async (vars) => {
      const previous: { queryKey: QueryKey; data: unknown }[] = [];
      for (const target of targets) {
        await queryClient.cancelQueries({ queryKey: target.queryKey });
        const data = queryClient.getQueryData(target.queryKey);
        if (data === undefined) continue;
        previous.push({ queryKey: target.queryKey, data });
        queryClient.setQueryData(target.queryKey, target.update(data, vars));
      }
      return { previous };
    },
    onError: (error, vars, context) => {
      for (const { queryKey, data } of context?.previous ?? []) queryClient.setQueryData(queryKey, data);
      onError?.(error, vars);
    },
    onSuccess,
    onSettled: () => {
      for (const target of targets) void queryClient.invalidateQueries({ queryKey: target.queryKey });
      for (const key of invalidate) void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}
