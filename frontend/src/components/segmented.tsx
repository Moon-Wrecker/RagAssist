import { motion } from "motion/react";
import { useId } from "react";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  /** A count shown after the label. Omit it while loading or failed, so no "0" appears beside an error. */
  count?: number;
}

/**
 * A segmented control: a thin glass track with a glass thumb that slides to the chosen option. Each option is a
 * toggle button (aria-pressed), so it works with the keyboard and screen readers without extra roles.
 */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  const thumb = useId();
  return (
    <div role="group" aria-label={label} className={cn("glass-thin relative inline-flex w-fit max-w-full rounded-full p-1", className)}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "press text-label relative inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 whitespace-nowrap transition-colors",
              active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {active ? (
              <motion.span
                layoutId={thumb}
                transition={spring.snappy}
                className="absolute inset-0 rounded-full bg-foreground/10 shadow-[inset_0_1px_0_oklch(1_0_0/0.25),0_1px_3px_oklch(0_0_0/0.25)]"
              />
            ) : null}
            <span className="relative">{option.label}</span>
            {option.count !== undefined ? <span className="text-meta relative opacity-70">{option.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
