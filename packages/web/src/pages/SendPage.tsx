import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import { SendForm } from "@/components/send/send-form";

export default function SendPage() {
  useDocumentTitle("Send Task");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Send Task"
        description="Dispatch a task to the Celery cluster"
      />

      <SendForm />
    </div>
  );
}
