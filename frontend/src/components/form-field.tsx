import { useId, type ComponentProps } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Label, input and optional hint wired together with ids so assistive technology reads them as one. */
export function FormField({
  label,
  hint,
  invalid = false,
  errorId,
  ...inputProps
}: { label: string; hint?: string; invalid?: boolean; errorId?: string } & Omit<ComponentProps<typeof Input>, "id">) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const describedBy = [hintId, invalid ? errorId : undefined].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} aria-invalid={invalid || undefined} aria-describedby={describedBy} {...inputProps} />
      {hint ? (
        <p id={hintId} className="text-[0.8125rem] text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
