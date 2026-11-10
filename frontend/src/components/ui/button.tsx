import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * Three levels. Primary is solid (white on dark, black on light) and there is one per view. Secondary is thin
 * glass. Ghost is text only. All are capsules, weight 500, and press to 0.97 with a spring settle (.press).
 * Row actions in tables are ghost or live in a menu; do not line up rows of secondary buttons.
 */
const buttonVariants = cva(
  "press inline-flex shrink-0 items-center justify-center gap-2 rounded-full text-label whitespace-nowrap select-none disabled:pointer-events-none disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-[0_1px_2px_oklch(0_0_0/0.25),0_4px_14px_-4px_oklch(0_0_0/0.35)]",
        secondary: "glass-thin glass-lens text-foreground",
        ghost: "text-foreground hover:bg-accent",
        link: "h-auto rounded-none p-0 text-foreground underline underline-offset-4 hover:decoration-2",
      },
      size: {
        default: "h-10 px-5",
        sm: "h-8 px-3.5",
        icon: "size-10",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean };

function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { Button, buttonVariants };
