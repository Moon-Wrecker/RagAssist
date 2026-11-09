import { useId, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth/auth-context";
import { captureFragmentToken, clearCapturedToken } from "@/auth/fragment-token";
import { AuthLayout } from "./auth-layout";
import { FormMessage } from "./form-message";
import { acceptLinkMessage } from "./messages";

/**
 * Spending a one-time link: the secret arrives in the URL fragment, is read once, scrubbed from the address bar,
 * and held in memory until the password is accepted. Invite and reset links share the same endpoint, so the two
 * pages share this form and differ only in wording.
 */
function SetPasswordForm({ title, intro, submitLabel }: { title: string; intro: string; submitLabel: string }) {
  const { actions } = useAuth();
  const navigate = useNavigate();
  const errorId = useId();
  // Read during the first render (idempotent, so StrictMode's second render sees the same value).
  const [token] = useState(captureFragmentToken);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !token) return;
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const repeat = String(form.get("repeat") ?? "");
    if (password !== repeat) {
      setError("The two passwords are different. Type the same password in both fields.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await actions.acceptLink({ token, password });
      clearCapturedToken();
      void navigate("/", { replace: true });
    } catch (caught) {
      setError(acceptLinkMessage(caught));
      setPending(false);
    }
  }

  if (!token) {
    return (
      <AuthLayout
        title="This link is incomplete"
        intro="The address is missing its one-time code. Open the full link an administrator sent you, or ask them for a new one."
      >
        <Button asChild variant="outline">
          <Link to="/sign-in">Go to sign in</Link>
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={title} intro={intro}>
      <form onSubmit={onSubmit} className="flex flex-col gap-5">
        <FormField
          label="New password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          maxLength={1024}
          hint="Use a long phrase you will remember. There are no other rules."
          invalid={error !== null}
          errorId={errorId}
        />
        <FormField
          label="Repeat the password"
          name="repeat"
          type="password"
          autoComplete="new-password"
          required
          maxLength={1024}
          invalid={error !== null}
          errorId={errorId}
        />
        <FormMessage id={errorId} message={error} />
        <Button type="submit" disabled={pending} aria-disabled={pending}>
          {pending ? "Saving" : submitLabel}
        </Button>
      </form>
    </AuthLayout>
  );
}

export function AcceptInvitePage() {
  return (
    <SetPasswordForm
      title="Set your password"
      intro="You have been invited to a workspace. Choose a password to finish setting up your account."
      submitLabel="Set password and sign in"
    />
  );
}

export function ResetPasswordPage() {
  return (
    <SetPasswordForm
      title="Choose a new password"
      intro="Your administrator sent you this link. Pick a new password; every other session will be signed out."
      submitLabel="Save password and sign in"
    />
  );
}
