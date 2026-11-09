import { ArrowUp, Square } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import type { ComposerState } from "./composer-state";

const MAX_HEIGHT_PX = 200;

/**
 * The message box, a floating glass layer under the thread. Enter sends, Shift+Enter adds a line. It is locked
 * while a turn runs (Stop replaces Send) and while an action waits for approval, and it says why.
 */
export function Composer({
  state,
  onSend,
  onStop,
}: {
  state: ComposerState;
  onSend: (text: string) => Promise<{ ok: boolean; error?: string }>;
  onStop: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const hintId = useId();
  const locked = state.lockedFor !== null;

  // Grow with the text up to a limit, then scroll.
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [draft]);

  // Give the box back to the person when a turn ends.
  const wasLocked = useRef(locked);
  useEffect(() => {
    if (wasLocked.current && !locked) ref.current?.focus({ preventScroll: true });
    wasLocked.current = locked;
  }, [locked]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (locked || draft.trim() === "") return;
    setError(null);
    const result = await onSend(draft);
    if (result.ok) setDraft("");
    else if (result.error) setError(result.error);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  const hint =
    state.lockedFor === "approval" || state.lockedFor === "deciding"
      ? "Decide on the action above to continue."
      : state.audience === "agent"
        ? "A support agent is handling this conversation. Your message goes to them."
        : null;
  const placeholder = state.audience === "agent" ? "Write to the support agent" : "Ask about your account or the documents";

  return (
    <form onSubmit={submit} className="glass-2 sticky bottom-3 z-30 mt-4 rounded-[1.75rem] py-2 pr-2 pl-5 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring" aria-label="Send a message">
      {hint ? (
        <p id={hintId} className="mt-1 mb-1 pr-3 font-mono text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-1 mb-1 pr-3 text-sm">
          {error}
        </p>
      ) : null}
      <div className="flex items-end gap-3">
        <textarea
          ref={ref}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          aria-label={state.label}
          aria-describedby={hint ? hintId : undefined}
          // Locked means "not now", not "disabled": it stays focusable and readable.
          readOnly={locked}
          aria-disabled={locked || undefined}
          placeholder={locked ? "" : placeholder}
          enterKeyHint="send"
          className="max-h-[200px] min-h-10 flex-1 resize-none bg-transparent py-2 text-base focus:outline-none leading-relaxed md:text-[0.9375rem] placeholder:text-muted-foreground aria-disabled:opacity-60"
        />
        {state.canStop ? (
          <Button type="button" variant="default" size="icon" className="rounded-full" onClick={onStop} aria-label="Stop the answer" title="Stop">
            <Square aria-hidden className="size-3.5 fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon" className="rounded-full" disabled={locked || draft.trim() === ""} aria-label="Send message" title="Send">
            <ArrowUp aria-hidden />
          </Button>
        )}
      </div>
    </form>
  );
}
