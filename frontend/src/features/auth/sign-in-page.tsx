import { useId, useState, type FormEvent } from "react";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth/auth-context";
import { AuthLayout } from "./auth-layout";
import { FormMessage } from "./form-message";
import { signInMessage } from "./messages";

const WORKSPACE_KEY = "ragassist-workspace";

// The workspace slug is not a secret; remembering it saves a field on the next visit.
function rememberedWorkspace(): string {
  try {
    return localStorage.getItem(WORKSPACE_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberWorkspace(slug: string): void {
  try {
    localStorage.setItem(WORKSPACE_KEY, slug);
  } catch {
    // Not remembered; harmless.
  }
}

export function SignInPage() {
  const { actions } = useAuth();
  const errorId = useId();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [defaultWorkspace] = useState(rememberedWorkspace);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const form = new FormData(event.currentTarget);
    const workspace = String(form.get("workspace") ?? "").trim();
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    setPending(true);
    setError(null);
    try {
      await actions.signIn({ workspace, email, password });
      rememberWorkspace(workspace);
      // Signed in: the PublicOnly guard around this route sends the visitor to the page they asked for.
    } catch (caught) {
      setError(signInMessage(caught));
      setPending(false);
    }
  }

  return (
    <AuthLayout title="Sign in" intro="Welcome back.">
      <form onSubmit={onSubmit} className="flex flex-col gap-5">
        <FormField
          label="Workspace"
          name="workspace"
          defaultValue={defaultWorkspace}
          autoComplete="organization"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          required
          maxLength={100}
          hint="The short name from your invite, like acme."
          invalid={error !== null}
          errorId={errorId}
        />
        <FormField
          label="Email"
          name="email"
          type="email"
          autoComplete="username"
          required
          maxLength={254}
          invalid={error !== null}
          errorId={errorId}
        />
        <FormField
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={1024}
          invalid={error !== null}
          errorId={errorId}
        />
        <FormMessage id={errorId} message={error} />
        <Button type="submit" disabled={pending} aria-disabled={pending}>
          {pending ? "Signing in" : "Sign in"}
        </Button>
        <p className="text-[0.8125rem] text-muted-foreground">
          No password yet? Open the link you were sent.
        </p>
      </form>
    </AuthLayout>
  );
}
