import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { useSearchParams } from "react-router";
import { ApiError, NetworkError } from "@/api/errors";
import { queryKeys } from "@/api/query-keys";
import { createConversation, decideAction, getConversation, listConversations, sendMessage } from "./api";
import { createFrameBatcher, type FrameBatcher } from "./batcher";
import { composerState, isHandoff } from "./composer-state";
import { readChatStream } from "./stream";
import { buildThread } from "./thread";
import { chatReducer, initialChatState, isSuperseded } from "./turn";

/** Query-string key that holds the open conversation, so a reload and the back button keep it. */
export const CONVERSATION_PARAM = "c";

const TITLE_LENGTH = 60;

/** A history title from the first message: its first line, trimmed to a readable length. */
export function titleFrom(text: string): string {
  const line = text.trim().split("\n", 1)[0]?.trim() ?? "";
  if (line === "") return "New conversation";
  return line.length > TITLE_LENGTH ? `${line.slice(0, TITLE_LENGTH - 1).trimEnd()}…` : line;
}

function describe(error: unknown): string {
  if (error instanceof NetworkError) return "The server could not be reached. Check your connection and try again.";
  if (error instanceof ApiError) {
    if (error.status === 429) return "Too many requests right now. Wait a moment and try again.";
    return error.detail ?? "The assistant could not answer. Try again.";
  }
  return "Something went wrong. Try again.";
}

/**
 * The chat screen's logic: which conversation is open, the live turn (a pure reducer fed by the stream), and the
 * calls to send, stop, retry and decide. Saved data (history, messages, status) is TanStack Query state that the
 * live-event invalidation keeps fresh, so an agent's reply appears without any code here.
 */
export function useChat() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const activeId = params.get(CONVERSATION_PARAM);
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const stateRef = useRef(state);
  // Handlers read the latest state through the ref; it is updated before the other effects of the same commit.
  useEffect(() => {
    stateRef.current = state;
  });

  const abortRef = useRef<AbortController | null>(null);
  const batcherRef = useRef<FrameBatcher | null>(null);
  /** Identifies the running send, so a late callback of an abandoned send cannot touch the current state. */
  const runRef = useRef(0);

  const conversation = useQuery({
    queryKey: queryKeys.conversation(activeId ?? ""),
    queryFn: () => getConversation(activeId ?? ""),
    enabled: activeId !== null,
  });
  const history = useQuery({ queryKey: queryKeys.conversations, queryFn: listConversations });

  const saved = conversation.data;
  const messages = useMemo(() => saved?.messages ?? [], [saved]);
  const { turn, notes } = state;

  const abandonRun = useCallback(() => {
    runRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    batcherRef.current?.discard();
    batcherRef.current = null;
  }, []);

  // Opening another conversation (or starting a new one) drops the live turn of the old one. Stop is safe: the
  // server finishes and saves the turn either way.
  useEffect(() => {
    const live = stateRef.current.turn.conversationId;
    if (live !== null && live !== activeId) {
      abandonRun();
      dispatch({ type: "switched" });
    }
  }, [activeId, abandonRun]);

  useEffect(() => abandonRun, [abandonRun]);

  // Once the saved messages show what the turn showed, hand over to them.
  useEffect(() => {
    if (turn.conversationId === activeId && isSuperseded(turn, messages.length)) dispatch({ type: "cleared" });
  }, [turn, activeId, messages.length]);

  const refetchSaved = useCallback(
    (conversationId: string) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations, exact: true }),
      ]),
    [queryClient],
  );

  const run = useCallback(
    async (conversationId: string, text: string, baseCount: number, wasEscalated: boolean) => {
      abandonRun();
      const myRun = runRef.current;
      const controller = new AbortController();
      abortRef.current = controller;
      const current = () => runRef.current === myRun;

      const batcher = createFrameBatcher((chunk) => {
        if (current()) dispatch({ type: "stream", event: { type: "token", text: chunk } });
      });
      batcherRef.current = batcher;
      dispatch({ type: "started", conversationId, question: text, baseCount, wasEscalated });

      try {
        const body = await sendMessage(conversationId, text, controller.signal);
        await readChatStream(body, (event) => {
          if (!current()) return;
          if (event.type === "token") {
            batcher.push(event.text);
            return;
          }
          if (event.type === "reset") batcher.discard();
          else batcher.flush();
          dispatch({ type: "stream", event });
        });
        if (!current()) return;
        batcher.flush();
        if (stateRef.current.turn.phase === "streaming") {
          dispatch({
            type: "failed",
            kind: "network",
            message: "The connection ended before the answer finished. The assistant may still save it.",
          });
        }
      } catch (error) {
        if (!current()) return;
        batcher.flush();
        if (error instanceof DOMException && error.name === "AbortError") dispatch({ type: "stopped" });
        else dispatch({ type: "failed", kind: error instanceof NetworkError ? "network" : "stream", message: describe(error) });
      } finally {
        if (current()) {
          abortRef.current = null;
          batcherRef.current = null;
          void refetchSaved(conversationId);
        }
      }
    },
    [abandonRun, refetchSaved],
  );

  const busy = turn.phase === "streaming" || turn.phase === "deciding";
  const status = turn.escalation && !turn.wasEscalated ? "escalated" : saved?.status;

  const send = useCallback(
    async (rawText: string, options: { baseCount?: number } = {}): Promise<{ ok: boolean; error?: string }> => {
      const text = rawText.trim();
      const live = stateRef.current.turn;
      if (text === "" || live.phase === "streaming" || live.phase === "deciding" || live.phase === "interrupted") return { ok: false };
      try {
        let conversationId = activeId;
        if (conversationId === null) {
          const created = await createConversation(titleFrom(text));
          conversationId = created.conversation_id;
          void queryClient.invalidateQueries({ queryKey: queryKeys.conversations, exact: true });
          // Start the turn before the address changes, so the switch effect sees the turn as this conversation's.
          const started = run(conversationId, text, 0, false);
          setParams({ [CONVERSATION_PARAM]: conversationId }, { replace: true });
          void started;
          return { ok: true };
        }
        const wasEscalated = isHandoff(status);
        void run(conversationId, text, options.baseCount ?? messages.length, wasEscalated);
        return { ok: true };
      } catch (error) {
        return { ok: false, error: describe(error) };
      }
    },
    [activeId, messages.length, queryClient, run, setParams, status],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retry = useCallback(() => {
    const { question, baseCount, phase } = stateRef.current.turn;
    if (phase !== "settled" || question === "") return;
    void send(question, { baseCount });
  }, [send]);

  const decide = useCallback(
    async (approved: boolean) => {
      const { turn: live } = stateRef.current;
      if (live.phase !== "interrupted" || !live.interrupt || live.conversationId === null) return;
      const conversationId = live.conversationId;
      dispatch({ type: "decision_started" });
      try {
        const result = await decideAction(conversationId, live.interrupt.interruptId, approved);
        dispatch({ type: "decision_resolved", approved, answer: result.answer, interrupt: result.interrupt });
        void refetchSaved(conversationId);
      } catch (error) {
        const message =
          error instanceof ApiError && error.status === 409
            ? "This action is no longer waiting for a decision. Reload the conversation to see where it stands."
            : describe(error);
        dispatch({ type: "decision_failed", message });
      }
    },
    [dispatch, refetchSaved],
  );

  const open = useCallback(
    (conversationId: string | null) => {
      setParams(conversationId ? { [CONVERSATION_PARAM]: conversationId } : {}, { replace: false });
    },
    [setParams],
  );

  const items = useMemo(() => buildThread(messages, notes, turn.conversationId === activeId ? turn : initialChatState.turn), [messages, notes, turn, activeId]);
  const composer = composerState(status, turn);

  return {
    activeId,
    conversation: saved,
    conversationError: conversation.isError ? conversation.error : null,
    conversationLoading: activeId !== null && conversation.isPending,
    reloadConversation: () => void conversation.refetch(),
    history,
    items,
    turn,
    status,
    composer,
    busy,
    send,
    stop,
    retry,
    decide,
    open,
  };
}
