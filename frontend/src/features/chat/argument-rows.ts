export interface ArgumentRow {
  name: string;
  value: string;
  /** Multi-line or structured values are shown in a block so nothing is cut or reflowed. */
  block: boolean;
}

/** The exact arguments of the action, one row per argument. Strings are shown as they are, other values as JSON. */
export function argumentRows(args: unknown): ArgumentRow[] {
  if (typeof args !== "object" || args === null || Array.isArray(args)) {
    return args === undefined || args === null ? [] : [{ name: "arguments", value: JSON.stringify(args, null, 2), block: true }];
  }
  return Object.entries(args as Record<string, unknown>).map(([name, value]) => {
    if (typeof value === "string") return { name, value, block: value.includes("\n") };
    const json = JSON.stringify(value, null, 2) ?? String(value);
    return { name, value: json, block: json.includes("\n") };
  });
}
