import { ArrowUp, Square } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type Ref } from "react";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group";
import { spring } from "@/lib/motion";
import type { ComposerState } from "./composer-state";

const MAX_HEIGHT_PX = 200;

/**
 * The message box: the one glass object in the chat column (regular thickness). Enter
 * sends, Shift+Enter adds a line, it grows with the text up to a limit. While a turn runs Send morphs into Stop;
 * while an action waits for approval it locks and says why. Locked means "not now", not "disabled": it stays
 * focusable and readable. Built on the Input Group (the AI Elements Prompt Input base).
 */
export function Composer({
  state,
  onSend,
  onStop,
  formRef,
  autoFocus = false,
}: {
  state: ComposerState;
  onSend: (text: string) => Promise<{ ok: boolean; error?: string }>;
  onStop: () => void;
  formRef?: Ref<HTMLFormElement>;
  autoFocus?: boolean;
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

  useEffect(() => {
    if (autoFocus) ref.current?.focus({ preventScroll: true });
  }, [autoFocus]);

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
      ? "Locked until you decide on the action above."
      : state.audience === "agent"
        ? "A support agent is handling this. Your message goes to them."
        : null;
  const placeholder = state.audience === "agent" ? "Write to the support agent" : "Ask about your account or the documents";

  return (
    <form
      ref={formRef}
      onSubmit={submit}
      aria-label="Send a message"
      className="glass-regular w-full rounded-(--r-outer) p-(--pad)"
      style={{ ["--r-outer" as string]: "1.75rem", ["--pad" as string]: "0.5rem" }}
    >
      <InputGroup>
        {hint ? (
          <p id={hintId} className="text-meta px-3 pt-1.5 pb-0.5 text-muted-foreground">
            {hint}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="px-3 pt-1.5 text-sm">
            {error}
          </p>
        ) : null}
        <div className="flex items-end gap-2">
          <InputGroupTextarea
            ref={ref}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            aria-label={state.label}
            aria-describedby={hint ? hintId : undefined}
            readOnly={locked}
            aria-disabled={locked || undefined}
            placeholder={locked ? "" : placeholder}
            enterKeyHint="send"
            className="max-h-[200px] min-h-10 px-3 py-2"
          />
          <InputGroupAddon align="inline-end" className="pb-0.5">
            <AnimatePresence mode="popLayout" initial={false}>
              {state.canStop ? (
                <motion.span key="stop" initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.7 }} transition={spring.snappy}>
                  <Button type="button" size="icon" onClick={onStop} aria-label="Stop the answer" title="Stop">
                    <Square aria-hidden className="size-3.5 fill-current" />
                  </Button>
                </motion.span>
              ) : (
                <motion.span key="send" initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.7 }} transition={spring.snappy}>
                  <Button type="submit" size="icon" disabled={locked || draft.trim() === ""} aria-label="Send message" title="Send">
                    <ArrowUp aria-hidden />
                  </Button>
                </motion.span>
              )}
            </AnimatePresence>
          </InputGroupAddon>
        </div>
      </InputGroup>
    </form>
  );
}
