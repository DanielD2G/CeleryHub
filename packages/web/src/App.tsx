import { BrowserRouter } from "react-router-dom";
import { EventProvider } from "./components/event-provider";
import { AppSidebar } from "./components/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "./components/ui/sidebar";
import { ErrorBoundary } from "./components/error-boundary";
import { AppRoutes } from "./router";
import { Toaster } from "sonner";

export default function App() {
  return (
    <BrowserRouter>
      <EventProvider>
        <SidebarProvider>
          <AppSidebar />
          <SidebarInset className="min-w-0">
            {/* Mobile-only header: without this trigger the off-canvas
                sidebar is unreachable on small screens. */}
            <header className="flex items-center gap-2 border-b px-4 py-2 md:hidden">
              <SidebarTrigger aria-label="Open navigation" />
              <span className="text-sm font-semibold">CeleryHub</span>
            </header>
            <div className="min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
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
