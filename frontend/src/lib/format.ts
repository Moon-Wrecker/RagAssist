const UNITS = ["B", "KB", "MB", "GB"] as const;

/** Binary sizes with the labels people expect ("50 MB"). One decimal below 10, none above. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const text = unit === 0 || value >= 10 ? String(Math.round(value)) : value.toFixed(1).replace(/\.0$/, "");
  return `${text} ${UNITS[unit]}`;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** "just now", "5 minutes ago", "2 days ago"; falls back to the date for anything older than a month. */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Math.max(0, now.getTime() - then);
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${plural(Math.floor(diff / MINUTE), "minute")} ago`;
  if (diff < DAY) return `${plural(Math.floor(diff / HOUR), "hour")} ago`;
  if (diff < 30 * DAY) return `${plural(Math.floor(diff / DAY), "day")} ago`;
  return formatDate(iso);
}

/** "in 3 days", "in 5 hours", or "expired". */
export function timeUntil(iso: string, now: Date = new Date()): string {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "";
  const diff = at - now.getTime();
  if (diff <= 0) return "expired";
  if (diff < HOUR) return `in ${plural(Math.max(1, Math.floor(diff / MINUTE)), "minute")}`;
  if (diff < DAY) return `in ${plural(Math.floor(diff / HOUR), "hour")}`;
  return `in ${plural(Math.floor(diff / DAY), "day")}`;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
