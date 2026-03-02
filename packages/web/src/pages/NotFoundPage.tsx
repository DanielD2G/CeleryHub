import { Link } from "react-router-dom";
import { useDocumentTitle } from "@/hooks/use-document-title";

export default function NotFoundPage() {
  useDocumentTitle("Not Found");

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center">
      <h1 className="text-6xl font-bold tracking-tight">404</h1>
      <p className="mt-2 text-lg text-muted-foreground">Page not found</p>
      <Link
        to="/"
        className="mt-6 text-sm text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
