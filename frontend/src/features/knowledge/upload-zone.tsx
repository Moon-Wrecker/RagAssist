import { X } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { UploadEntry } from "./documents-logic";
import { ACCEPT_ATTRIBUTE, ACCEPTED_SUMMARY } from "./upload-validation";

/**
 * Drag and drop plus a file picker. Both hand the chosen files to `onFiles`; validation and upload live in the page.
 * The picker button is the keyboard path, so nothing depends on dragging.
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
  // dragenter and dragleave also fire for child elements, so count them to know when the pointer truly left.
  const depth = useRef(0);

  function hasFiles(event: DragEvent): boolean {
    return Array.from(event.dataTransfer.types).includes("Files");
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragEnter={(event) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          depth.current += 1;
          setDragging(true);
        }}
        onDragOver={(event) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={() => {
          depth.current = Math.max(0, depth.current - 1);
          if (depth.current === 0) setDragging(false);
        }}
        onDrop={(event) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          depth.current = 0;
          setDragging(false);
          const files = Array.from(event.dataTransfer.files);
          if (files.length > 0) onFiles(files);
        }}
        role="group"
        aria-label="Add documents by dropping files"
        data-dragging={dragging || undefined}
        className={cn(
          "flex flex-col items-start gap-3 rounded-2xl border border-dashed border-border-strong p-5 transition-colors sm:flex-row sm:items-center sm:justify-between",
          dragging && "border-solid border-foreground bg-accent",
        )}
      >
        <div>
          <p className="font-medium">{dragging ? "Drop the files to upload them" : "Drag files here to add them"}</p>
          <p id={hintId} className="mt-1 text-sm text-muted-foreground">
            {ACCEPTED_SUMMARY}.
          </p>
        </div>
        <Button type="button" onClick={() => inputRef.current?.click()} aria-describedby={hintId}>
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
        <ul aria-label="Uploads in progress" className="flex flex-col divide-y rounded-2xl border">
          {entries.map((entry) => (
            <li key={entry.id} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{entry.name}</p>
                {entry.state === "uploading" ? (
                  <p className="mt-0.5 font-mono text-xs text-muted-foreground">Uploading {formatBytes(entry.size)}</p>
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
                <Button type="button" variant="ghost" size="sm" aria-label={`Dismiss the message about ${entry.name}`} onClick={() => onDismiss(entry.id)}>
                  <X aria-hidden />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
