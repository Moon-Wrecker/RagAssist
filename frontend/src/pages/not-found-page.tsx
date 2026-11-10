import { Link } from "react-router";
import { StatusPage } from "@/components/status-page";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <StatusPage title="No page here" body="That page does not exist.">
      <Button asChild variant="secondary">
        <Link to="/">Go to the start page</Link>
      </Button>
    </StatusPage>
  );
}
