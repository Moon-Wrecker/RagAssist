import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { UploadEntry } from "./documents-logic";
import { ACCEPT_ATTRIBUTE, ACCEPTED_SUMMARY } from "./upload-validation";

function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files");
}

/**
 * A slim dashed strip with the one primary button. While files are dragged anywhere over the window it reacts: the
 * strip turns solid and a dashed frame fades in over the page; a drop anywhere adds the files. The picker button is
 * the keyboard path, so nothing depends on dragging. Validation and upload live in the page.
 */
export function UploadZone({
  entries,
  onFiles,
  onDismiss,
}: {
  entries: UploadEntry[];
  onFiles: (files: File[]) => void;
  onDismiss: (id: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [dragging, setDragging] = useState(false);
  const onFilesRef = useRef(onFiles);
  useEffect(() => {
    onFilesRef.current = onFiles;
  });

  // Window-level drag handling. dragenter and dragleave also fire for child elements, so count them to know when
  // the pointer truly left the window. A layout effect so the listeners exist as soon as the strip is on screen.
  useLayoutEffect(() => {
    let depth = 0;
    const enter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth += 1;
      setDragging(true);
    };
    const over = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    };
    const leave = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const drop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth = 0;
      setDragging(false);
      const files = Array.from(event.dataTransfer?.files ?? []);
      if (files.length > 0) onFilesRef.current(files);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, []);

  return (
    <div className="flex flex-col gap-2">
      <div
        role="group"
        aria-label="Add documents by dropping files"
        data-dragging={dragging || undefined}
        className={cn(
          "flex items-center justify-between gap-3 rounded-full border border-dashed border-border-strong py-2 pr-2 pl-5 transition-colors duration-(--dur-base)",
          dragging && "border-solid border-foreground bg-accent",
        )}
      >
        <p id={hintId} className="min-w-0 truncate text-sm text-muted-foreground">
          {dragging ? "Drop the files to upload them" : `Drop files here. ${ACCEPTED_SUMMARY}.`}
        </p>
        <Button type="button" size="sm" onClick={() => inputRef.current?.click()} aria-describedby={hintId}>
          Choose files
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          aria-label="Choose documents to upload"
          tabIndex={-1}
          className="sr-only"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            // Reset so choosing the same file again still fires a change.
            event.target.value = "";
            if (files.length > 0) onFiles(files);
          }}
        />
      </div>

      {entries.length > 0 ? (
        <ul aria-label="Uploads in progress" className="flex flex-col divide-y divide-border px-2">
          {entries.map((entry) => (
            <li key={entry.id} className="flex items-start justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{entry.name}</p>
                {entry.state === "uploading" ? (
                  <p className="text-meta mt-0.5 text-muted-foreground">Uploading {formatBytes(entry.size)}</p>
                ) : (
                  <p className="mt-0.5 border-l-2 border-dashed border-foreground pl-3 text-[0.8125rem]">
                    <span aria-hidden className="mr-2 font-mono font-medium">
                      !
                    </span>
                    {entry.message}
                  </p>
                )}
              </div>
              {entry.state !== "uploading" ? (
                <Button type="button" variant="ghost" size="icon-sm" aria-label={`Dismiss the message about ${entry.name}`} onClick={() => onDismiss(entry.id)}>
                  <X aria-hidden />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <AnimatePresence>
        {dragging ? (
          <motion.div
            aria-hidden
            className="glass-thick pointer-events-none fixed inset-(--gutter) z-40 flex items-center justify-center rounded-(--r-surface) border-2 border-dashed border-foreground"
            initial={{ opacity: 0, scale: 0.985 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.985 }}
            transition={{ duration: 0.16 }}
          >
            <p className="font-heading">Drop the files to add them</p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
