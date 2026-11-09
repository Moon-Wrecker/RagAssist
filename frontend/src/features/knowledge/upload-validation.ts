import { formatBytes } from "@/lib/format";

/**
 * Client-side checks that mirror what the API enforces, so a bad file is refused instantly and in plain words
 * instead of after a long upload. The server still decides (413 over the size cap, 415 for an unsupported type,
 * 400 for an empty file); see `describeUploadError`.
 *
 * Source of truth: `MAX_UPLOAD_BYTES` in the knowledge router (50 MiB) and the allowed MIME set in
 * `UploadDocument` (Markdown, HTML, CSV, PDF).
 */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

interface FileKind {
  label: string;
  mime: string;
  extensions: readonly string[];
}

export const FILE_KINDS: readonly FileKind[] = [
  { label: "PDF", mime: "application/pdf", extensions: [".pdf"] },
  { label: "Markdown", mime: "text/markdown", extensions: [".md", ".markdown"] },
  { label: "HTML", mime: "text/html", extensions: [".html", ".htm"] },
  { label: "CSV", mime: "text/csv", extensions: [".csv"] },
];

/** For the file picker's `accept` attribute. */
export const ACCEPT_ATTRIBUTE = FILE_KINDS.flatMap((kind) => kind.extensions).join(",");

export const ACCEPTED_SUMMARY = `${FILE_KINDS.map((kind) => kind.label).join(", ")}; up to ${formatBytes(MAX_UPLOAD_BYTES)} each`;

export interface UploadCandidate {
  name: string;
  size: number;
}

export type UploadCheck = { ok: true; mime: string } | { ok: false; code: "empty" | "too-large" | "type"; reason: string };

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot <= 0 ? "" : name.slice(dot).toLowerCase();
}

/** The MIME type the API expects for a file name, or null if the name has no supported extension. */
export function mimeForName(name: string): string | null {
  const extension = extensionOf(name);
  return FILE_KINDS.find((kind) => kind.extensions.includes(extension))?.mime ?? null;
}

/**
 * The type is decided by the file extension, not by what the browser reports: browsers disagree (a `.csv` can
 * arrive as `application/vnd.ms-excel` on Windows, a `.md` as nothing at all), and the upload sends the
 * extension's type explicitly.
 */
export function validateUpload(file: UploadCandidate): UploadCheck {
  const mime = mimeForName(file.name);
  if (mime === null) {
    return {
      ok: false,
      code: "type",
      reason: `${file.name} is not a supported type. Use ${FILE_KINDS.map((kind) => kind.label).join(", ")}.`,
    };
  }
  if (file.size === 0) {
    return { ok: false, code: "empty", reason: `${file.name} is empty. Choose a file that has content.` };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      ok: false,
      code: "too-large",
      reason: `${file.name} is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_UPLOAD_BYTES)} per file.`,
    };
  }
  return { ok: true, mime };
}
