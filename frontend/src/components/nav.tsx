import { BookOpen, Inbox, MessageCircle, Users, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { NavLink } from "react-router";
import type { AppRoute } from "@/app/access";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  "/": MessageCircle,
  "/inbox": Inbox,
  "/knowledge": BookOpen,
  "/team": Users,
};

/**
 * One navigation entry. The active entry carries a glass thumb that slides to the next one (a shared layout
 * animation: transform only). `orientation` picks the sidebar row or the phone tab.
 */
export function NavEntry({
  route,
  orientation,
  collapsed = false,
  thumbId,
}: {
  route: AppRoute;
  orientation: "row" | "tab";
  collapsed?: boolean;
  thumbId: string;
}) {
  const Icon = ICONS[route.path] ?? MessageCircle;
  return (
    <NavLink
      to={route.path}
      end={route.path === "/"}
      title={collapsed ? route.label : undefined}
      aria-label={collapsed ? route.label : undefined}
      className={({ isActive }) =>
        cn(
          "press relative flex items-center rounded-full text-label text-muted-foreground hover:text-foreground",
          orientation === "row"
            ? cn("h-10 gap-3", collapsed ? "w-10 justify-center self-center" : "px-3.5")
            : "h-12 flex-1 flex-col justify-center gap-0.5 text-[0.6875rem]",
          isActive && "text-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive ? (
            <motion.span layoutId={thumbId} transition={spring.glide} aria-hidden className="glass-thin absolute inset-0 rounded-full" />
          ) : null}
          <Icon aria-hidden className="relative size-[1.125rem] shrink-0" strokeWidth={isActive ? 2.1 : 1.75} />
          {collapsed ? null : <span className="relative">{route.label}</span>}
        </>
      )}
    </NavLink>
  );
}
