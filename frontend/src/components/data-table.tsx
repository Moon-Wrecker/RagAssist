import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * A table that sits directly on a thick glass surface (see TableSurface): the header row sticks and is translucent,
 * so rows scroll under it; rows are separated by hairlines and only the hovered row gets thin glass. From the `sm`
 * breakpoint up it is an ordinary table; on phones each row becomes a stacked block and each cell shows its column
 * name (from `label`) beside the value. Explicit ARIA roles keep the table semantics when CSS changes the display.
 */
export function DataTable({ className, ...props }: ComponentProps<"table">) {
  return <table role="table" className={cn("w-full border-separate border-spacing-0 text-left text-sm", className)} {...props} />;
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("sr-only", className)} {...props} />;
}

export function THead({ className, ...props }: ComponentProps<"thead">) {
  return <thead role="rowgroup" className={cn("max-sm:sr-only", className)} {...props} />;
}

export function TBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody role="rowgroup" className={cn("max-sm:block [&>tr:first-child>td]:border-t-0", className)} {...props} />;
}

export function Tr({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      role="row"
      className={cn("row-hover max-sm:block max-sm:border-t max-sm:border-border max-sm:px-5 max-sm:py-3.5 max-sm:first:border-t-0", className)}
      {...props}
    />
  );
}

export function Th({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      role="columnheader"
      scope="col"
      className={cn(
        "sticky-glass sticky top-0 z-10 border-b border-border px-4 py-2.5 text-meta font-medium text-muted-foreground first:pl-6 last:pr-6",
        className,
      )}
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
        "px-4 py-3 align-middle first:pl-6 last:pr-6 sm:border-t sm:border-border",
        "max-sm:flex max-sm:items-center max-sm:justify-between max-sm:gap-4 max-sm:px-0 max-sm:py-1 max-sm:first:pl-0 max-sm:last:pr-0",
        label && !primary && "max-sm:before:text-meta max-sm:before:text-muted-foreground max-sm:before:content-[attr(data-label)]",
        primary && "max-sm:block max-sm:pb-1.5 max-sm:text-base max-sm:font-medium",
        className,
      )}
      {...props}
    />
  );
}
