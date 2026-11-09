import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { useSignedIn } from "@/auth/auth-context";

/** A real route with a plain empty state, so navigation and role guards work before each screen is built. */
export function PlaceholderPage({ title, children }: { title: string; children: ReactNode }) {
  const { user, workspace } = useSignedIn();
  return (
    <Panel className="max-w-2xl">
      <h1 className="font-heading text-5xl sm:text-6xl">{title}</h1>
      <p className="mt-4 text-muted-foreground">{children}</p>
      <p className="mt-8 font-mono text-xs text-muted-foreground">
        {workspace.slug} / {user.email} / {user.role}
      </p>
    </Panel>
  );
}
