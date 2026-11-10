import { Link } from "react-router";
import { StatusPage } from "@/components/status-page";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <StatusPage title="No page here" body="The address does not match anything in the app.">
      <Button asChild variant="secondary">
        <Link to="/">Go to the start page</Link>
      </Button>
    </StatusPage>
  );
}
