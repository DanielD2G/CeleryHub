import { Routes, Route } from "react-router-dom";
import { lazy, Suspense } from "react";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ActivePage = lazy(() => import("./pages/ActivePage"));
const TasksPage = lazy(() => import("./pages/TasksPage"));
const TaskGroupPage = lazy(() => import("./pages/TaskGroupPage"));
const SendPage = lazy(() => import("./pages/SendPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));
const WorkersPage = lazy(() => import("./pages/WorkersPage"));
const QueuesPage = lazy(() => import("./pages/QueuesPage"));
const BeatsPage = lazy(() => import("./pages/BeatsPage"));
const BeatDetailPage = lazy(() => import("./pages/BeatDetailPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

export function AppRoutes() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          Loading...
        </div>
      }
    >
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/active" element={<ActivePage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/tasks/:name" element={<TaskGroupPage />} />
        <Route path="/send" element={<SendPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/workers" element={<WorkersPage />} />
        <Route path="/queues" element={<QueuesPage />} />
        <Route path="/beats" element={<BeatsPage />} />
        <Route path="/beats/:id" element={<BeatDetailPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
