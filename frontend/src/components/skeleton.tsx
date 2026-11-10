import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** A placeholder bar. The skeletons below mirror the final layouts so nothing jumps when the data arrives. */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div aria-hidden className={cn("skeleton h-3", className)} {...props} />;
}

/** Rows shaped like a data table: a wide first cell, then short ones. The width varies a little so it reads as text. */
export function TableSkeleton({ columns = 4, rows = 6, label }: { columns?: number; rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="w-full">
      <div className="flex gap-6 border-b border-border px-6 py-3.5">
        {Array.from({ length: columns }, (_, column) => (
          <Skeleton key={column} className={cn("h-2.5", column === 0 ? "w-24" : "w-14")} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="flex items-center gap-6 border-t border-border px-6 py-4 first:border-t-0">
          {Array.from({ length: columns }, (_, column) => (
            <Skeleton
              key={column}
              className={column === 0 ? "flex-[3]" : "flex-1"}
              style={column === 0 ? { maxWidth: `${62 - ((row * 7) % 22)}%` } : undefined}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Rows shaped like the inbox list: a marker, a line of text and a time, then a short second line. */
export function ListSkeleton({ rows = 6, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="w-full">
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="flex flex-col gap-2 border-t border-border px-5 py-3.5 first:border-t-0">
          <div className="flex items-center gap-3">
            <Skeleton className="size-2.5" />
            <Skeleton className="flex-1" style={{ maxWidth: `${80 - ((row * 11) % 30)}%` }} />
            <Skeleton className="ml-auto w-8" />
          </div>
          <Skeleton className="ml-5.5 h-2.5 w-20" />
        </div>
      ))}
    </div>
  );
}

/** Lines shaped like a thread: a short label, then two lines of text, repeated. */
export function ThreadSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-7 px-6 py-6">
      {[68, 92, 54, 80].map((width, index) => (
        <div key={index} className="flex flex-col gap-2.5 border-l-2 border-border pl-4">
          <Skeleton className="h-2.5 w-16" />
          <Skeleton style={{ width: `${width}%` }} />
          <Skeleton style={{ width: `${Math.max(30, width - 24)}%` }} />
        </div>
      ))}
    </div>
  );
}
