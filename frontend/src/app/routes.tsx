import { Route, Routes } from "react-router";
import { AppShell } from "@/components/app-shell";
import { PublicOnly, RequireAuth, RequireRole } from "@/auth/guards";
import { AcceptInvitePage, ResetPasswordPage } from "@/features/auth/set-password-page";
import { SignInPage } from "@/features/auth/sign-in-page";
import { ChatPage } from "@/features/chat/chat-page";
import { InboxPage } from "@/features/inbox/inbox-page";
import { KnowledgePage } from "@/features/knowledge/knowledge-page";
import { TeamPage } from "@/features/team/team-page";
import { NotFoundPage } from "@/pages/not-found-page";
import { APP_ROUTES } from "./access";

function rolesOf(path: string) {
  const route = APP_ROUTES.find((candidate) => candidate.path === path);
  if (!route) throw new Error(`No route is registered for ${path}`);
  return route.roles;
}

/** The route tree. Roles come from the same table as the navigation (app/access.ts). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicOnly />}>
        <Route path="/sign-in" element={<SignInPage />} />
      </Route>
      {/* Invite and reset links are spendable while signed in too, so they sit outside PublicOnly. */}
      <Route path="/accept" element={<AcceptInvitePage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route element={<RequireRole roles={rolesOf("/")} />}>
            <Route index element={<ChatPage />} />
          </Route>
          <Route element={<RequireRole roles={rolesOf("/inbox")} />}>
            <Route path="/inbox" element={<InboxPage />} />
          </Route>
          <Route element={<RequireRole roles={rolesOf("/knowledge")} />}>
            <Route path="/knowledge" element={<KnowledgePage />} />
          </Route>
          <Route element={<RequireRole roles={rolesOf("/team")} />}>
            <Route path="/team" element={<TeamPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
