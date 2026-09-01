import { BrowserRouter } from "react-router-dom";
import { EventProvider } from "./components/event-provider";
import { AppSidebar } from "./components/app-sidebar";
import { SidebarInset, SidebarProvider } from "./components/ui/sidebar";
import { ErrorBoundary } from "./components/error-boundary";
import { AppRoutes } from "./router";
import { Toaster } from "sonner";

export default function App() {
  return (
    <BrowserRouter>
      <EventProvider>
        <SidebarProvider>
          <AppSidebar />
          <SidebarInset>
            <div className="flex-1 overflow-y-auto p-4 md:p-6">
              <ErrorBoundary>
                <AppRoutes />
              </ErrorBoundary>
            </div>
            <Toaster richColors position="bottom-right" />
          </SidebarInset>
        </SidebarProvider>
      </EventProvider>
    </BrowserRouter>
  );
}
