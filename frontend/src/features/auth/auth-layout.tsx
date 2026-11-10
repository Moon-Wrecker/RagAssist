import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { ThemeToggle } from "@/components/theme-toggle";
import { Wordmark } from "@/components/wordmark";

/**
 * Frame for the signed-out screens: the product name and the theme switch float in the corners, and one thick glass
 * panel with a serif title and the form sits in the middle of the liquid. No hero, no illustration, no top bar.
 */
export function AuthLayout({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return (
    <div className="scroll-area flex h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="flex shrink-0 items-center justify-between px-6 pt-5">
        <Wordmark />
        <ThemeToggle />
      </header>
      <main id="main" className="m-auto w-full max-w-md px-(--gutter) py-8">
        <Panel>
          <h1 className="font-heading">{title}</h1>
          <p className="mt-2 text-muted-foreground">{intro}</p>
          <div className="mt-7">{children}</div>
        </Panel>
      </main>
    </div>
  );
}
