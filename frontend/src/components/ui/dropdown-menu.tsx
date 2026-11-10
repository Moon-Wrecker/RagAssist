import { MoreHorizontal } from "lucide-react";
import { DropdownMenu as MenuPrimitive } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * shadcn's Dropdown Menu on a thick glass panel. Rows are plain; the highlighted item gets the same thin-glass
 * hover as a table row. Radix supplies the keyboard behaviour (arrows, type-ahead, Escape, focus return).
 */
const Menu = MenuPrimitive.Root;
const MenuTrigger = MenuPrimitive.Trigger;

function MenuContent({ className, sideOffset = 6, ...props }: ComponentProps<typeof MenuPrimitive.Content>) {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Content
        sideOffset={sideOffset}
        align="end"
        className={cn("glass-thick fade-in z-50 min-w-44 rounded-2xl p-1.5 text-popover-foreground", className)}
        {...props}
      />
    </MenuPrimitive.Portal>
  );
}

function MenuItem({ className, ...props }: ComponentProps<typeof MenuPrimitive.Item>) {
  return (
    <MenuPrimitive.Item
      className={cn(
        "flex cursor-default items-center gap-2.5 rounded-xl px-3 py-2 text-sm outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-45 data-[highlighted]:bg-accent [&_svg]:size-4 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    />
  );
}

/** The "more" button at the end of a table row. `label` names it for assistive technology ("Actions for report.pdf"). */
function RowMenu({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={label}>
          <MoreHorizontal aria-hidden />
        </Button>
      </MenuTrigger>
      <MenuContent>{children}</MenuContent>
    </Menu>
  );
}

export { Menu, MenuTrigger, MenuContent, MenuItem, RowMenu };
