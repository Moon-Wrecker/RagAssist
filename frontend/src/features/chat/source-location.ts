/** Where a passage sits in its document, as one line of mono metadata. */
export function sourceLocation(parts: { headingPath?: readonly string[]; page?: number | null }): string {
  const path = (parts.headingPath ?? []).filter((part) => part !== "").join(" / ");
  const page = typeof parts.page === "number" ? `p. ${parts.page}` : "";
  return [path, page].filter((part) => part !== "").join("  ·  ");
}
