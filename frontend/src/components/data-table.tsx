import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * Plain, accessible table markup. From the `sm` breakpoint up it is an ordinary table; on phones each row becomes
 * a stacked block and each cell shows its column name (from `label`) beside the value. Explicit ARIA roles keep the
 * table semantics for screen readers when CSS changes the display type.
 *
 * Put it directly in a glass-1 panel: do not wrap rows in cards.
 */
export function DataTable({ className, ...props }: ComponentProps<"table">) {
  return <table role="table" className={cn("w-full border-collapse text-left text-sm", className)} {...props} />;
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("sr-only", className)} {...props} />;
}

export function THead({ className, ...props }: ComponentProps<"thead">) {
  return <thead role="rowgroup" className={cn("max-sm:sr-only", className)} {...props} />;
}

export function TBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody role="rowgroup" className={cn("max-sm:block", className)} {...props} />;
}

export function Tr({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      role="row"
      className={cn("border-t first:border-t-0 max-sm:block max-sm:px-4 max-sm:py-3 sm:hover:bg-accent/50", className)}
      {...props}
    />
  );
}

export function Th({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      role="columnheader"
      scope="col"
      className={cn("px-4 py-2.5 font-mono text-xs font-medium text-muted-foreground", className)}
      {...props}
    />
  );
}

/**
 * `label` is the column name shown beside the value when the row is stacked. `primary` marks the cell that names the
 * row (file name, email); it spans the full width when stacked and needs no label.
 */
export function Td({
  className,
  label,
  primary = false,
  ...props
}: ComponentProps<"td"> & { label?: string; primary?: boolean }) {
  return (
    <td
      role="cell"
      data-label={label}
      className={cn(
        "px-4 py-3 align-middle",
        "max-sm:flex max-sm:items-center max-sm:justify-between max-sm:gap-4 max-sm:px-0 max-sm:py-1",
        label && !primary && "max-sm:before:font-mono max-sm:before:text-xs max-sm:before:text-muted-foreground max-sm:before:content-[attr(data-label)]",
        primary && "max-sm:block max-sm:pb-1.5 max-sm:text-base max-sm:font-medium",
        className,
      )}
      {...props}
    />
  );
}
