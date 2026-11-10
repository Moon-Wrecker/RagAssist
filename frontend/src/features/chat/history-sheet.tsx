import type { RefObject } from "react";
import { HistoryList } from "@/components/history-list";
import { GlassSheet } from "./glass-sheet";

/** Phones: the same history list as the sidebar, in a thick glass sheet. Choosing one opens it and closes the sheet. */
export function HistorySheet({
  open,
  onOpenChange,
  activeId,
  onSelect,
  onNew,
  returnFocusTo,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  returnFocusTo: RefObject<HTMLElement | null>;
}) {
  return (
    <GlassSheet
      open={open}
      onOpenChange={onOpenChange}
      placement="bottom"
      title="History"
      description="Your past conversations. Choose one to open it."
      returnFocusTo={returnFocusTo}
    >
      <div className="flex h-[60dvh] flex-col">
        <HistoryList activeId={activeId} onSelect={onSelect} onNew={onNew} />
      </div>
    </GlassSheet>
  );
}
