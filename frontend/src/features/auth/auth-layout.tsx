import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { ThemeToggle } from "@/components/theme-toggle";
import { Wordmark } from "@/components/wordmark";

/**
 * Frame for the signed-out screens: a glass top bar, then one glass panel holding the title and form, left
 * aligned in a narrow column over the monochrome backdrop. No hero, no illustration.
 */
export function AuthLayout({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="glass-2 sticky top-0 z-40 border-x-0! border-t-0!">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Wordmark />
          <ThemeToggle />
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 pt-8 pb-16 sm:px-6 sm:pt-[10vh]">
        <Panel className="max-w-md">
          <h1 className="font-heading text-5xl sm:text-6xl">{title}</h1>
          <p className="mt-4 text-muted-foreground">{intro}</p>
          <div className="mt-8">{children}</div>
        </Panel>
      </main>
    </div>
  );
}
