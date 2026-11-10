import { useRef, useState } from "react";
import type { IssuedLink } from "@/api/team";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { timeUntil } from "@/lib/format";

export type IssuedKind = "invite" | "reset";

/**
 * Shows a one-time link. The server returns it once and keeps only a hash, so this dialog is the only chance to
 * copy it; closing it forgets the link (the parent clears its state).
 */
export function IssuedLinkDialog({
  link,
  kind,
  onClose,
}: {
  link: IssuedLink | null;
  kind: IssuedKind;
  onClose: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");

  async function copyLink() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.url);
      setCopy("copied");
    } catch {
      // No clipboard permission (or an insecure context): select the text so Ctrl+C works.
      inputRef.current?.select();
      setCopy("failed");
    }
  }

  return (
    <Dialog
      open={link !== null}
      onOpenChange={(open) => {
        if (!open) {
          setCopy("idle");
          onClose();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{kind === "invite" ? "Invite link ready" : "Password reset link ready"}</DialogTitle>
          <DialogDescription>
            {link ? (
              <>
                For <span className="font-medium text-foreground break-all">{link.email}</span>. This link is shown only
                once. Copy it now and send it to them yourself; it expires {timeUntil(link.expires_at)}. If you lose it,
                revoke it and create a new one.
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2 px-6 py-5">
          <Label htmlFor="issued-link">One-time link</Label>
          <Input
            id="issued-link"
            ref={inputRef}
            readOnly
            value={link?.url ?? ""}
            onFocus={(event) => event.currentTarget.select()}
            className="font-mono text-xs"
          />
          <p role="status" aria-live="polite" className="min-h-5 text-[0.8125rem] text-muted-foreground">
            {copy === "copied" ? "Copied to the clipboard." : copy === "failed" ? "Could not copy automatically. The link is selected: press Ctrl or Cmd + C." : ""}
          </p>
        </div>
        <div className="flex justify-end gap-2 px-6 pb-6">
          <Button variant="secondary" onClick={() => void copyLink()}>
            Copy link
          </Button>
          <Button onClick={onClose}>Done</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
