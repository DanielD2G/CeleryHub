import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useCelery } from "@/hooks/use-celery";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import type { CompletedTaskMeta } from "@/lib/types";
import { statusVariant } from "@/lib/task-utils";
import { TaskDetailDialog } from "@/components/tasks/task-detail-dialog";
import { Badge } from "@/components/ui/badge";
import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
  PaginationEllipsis,
} from "@/components/ui/pagination";
import { Search, Copy, Check } from "lucide-react";

const PAGE_SIZE = 20;

const COLUMNS = [
  { key: "name", label: "Task Name", defaultWidth: 220, minWidth: 100 },
  { key: "id", label: "ID", defaultWidth: 300, minWidth: 100 },
  { key: "worker", label: "Worker", defaultWidth: 150, minWidth: 80 },
  { key: "status", label: "Status", defaultWidth: 100, minWidth: 70 },
  { key: "runtime", label: "Runtime", defaultWidth: 100, minWidth: 70 },
  { key: "completed", label: "Completed", defaultWidth: 180, minWidth: 100 },
] as const;

function useColumnResize() {
  const [widths, setWidths] = useState<number[]>(() =>
    COLUMNS.map((c) => c.defaultWidth)
  );
  const active = useRef(false);
  const colIndex = useRef(0);
  const startX = useRef(0);
  const startW = useRef(0);

  const onPointerDown = useCallback(
    (e: React.PointerEvent, idx: number) => {
      e.preventDefault();
      e.stopPropagation();
      active.current = true;
      colIndex.current = idx;
      startX.current = e.clientX;
      startW.current = widths[idx];
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [widths]
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!active.current) return;
      const dx = e.clientX - startX.current;
      const col = COLUMNS[colIndex.current];
      const newW = Math.max(col.minWidth, startW.current + dx);
      setWidths((prev) => {
        const next = [...prev];
        next[colIndex.current] = newW;
        return next;
      });
    },
    []
  );

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    if (!active.current) return;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    active.current = false;
  }, []);

  return { widths, onPointerDown, onPointerMove, onPointerUp };
}

function getPageNumbers(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const pages: (number | "ellipsis")[] = [1];

  if (current > 3) pages.push("ellipsis");

  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) pages.push(i);

  if (current < total - 2) pages.push("ellipsis");

  pages.push(total);
  return pages;
}

export default function HistoryPage() {
  useDocumentTitle("Results");
  const { completedTasks } = useCelery();
  const [selected, setSelected] = useState<CompletedTaskMeta | null>(null);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState<Date | undefined>();
  const [dateTo, setDateTo] = useState<Date | undefined>();
  const [page, setPage] = useState(1);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    if (!copiedId) return;
    const t = setTimeout(() => setCopiedId(null), 1500);
    return () => clearTimeout(t);
  }, [copiedId]);

  const filtered = useMemo(() => {
    const all = Array.from(completedTasks.values()).sort(
      (a, b) => b.completedAt - a.completedAt
    );
    const fromTs = dateFrom ? dateFrom.getTime() / 1000 : 0;
    const toTs = dateTo ? dateTo.getTime() / 1000 : Infinity;
    const q = search.trim().toLowerCase();

    return all.filter((t) => {
      if (t.completedAt < fromTs || t.completedAt > toTs) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) ||
        t.taskId.toLowerCase().includes(q) ||
        t.worker.toLowerCase().includes(q) ||
        t.status.toLowerCase().includes(q)
      );
    });
  }, [completedTasks, search, dateFrom, dateTo]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paginated = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
  };
  const handleDateFrom = (value: Date | undefined) => {
    setDateFrom(value);
    setPage(1);
  };
  const handleDateTo = (value: Date | undefined) => {
    setDateTo(value);
    setPage(1);
  };

  const { widths, onPointerDown, onPointerMove, onPointerUp } = useColumnResize();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Results"
        description="Completed task executions"
      />

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by name, ID, worker or status..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <DatePicker
          value={dateFrom}
          onChange={handleDateFrom}
          placeholder="From"
        />
        <DatePicker
          value={dateTo}
          onChange={handleDateTo}
          placeholder="To"
        />
      </div>

      {filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {search
            ? "No tasks match your search."
            : "No completed tasks yet. Tasks will appear here as they finish."}
        </p>
      ) : (
        <>
          <Table className="table-fixed">
            <colgroup>
              {widths.map((w, i) => (
                <col key={COLUMNS[i].key} style={{ width: w }} />
              ))}
            </colgroup>
            <TableHeader>
              <TableRow>
                {COLUMNS.map((col, i) => (
                  <TableHead key={col.key} className="relative overflow-hidden">
                    <span className="truncate">{col.label}</span>
                    {i < COLUMNS.length - 1 && (
                      <span
                        className="absolute inset-y-0 -right-px z-10 w-2 cursor-col-resize select-none hover:bg-border"
                        onPointerDown={(e) => onPointerDown(e, i)}
                        onPointerMove={onPointerMove}
                        onPointerUp={onPointerUp}
                      />
                    )}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginated.map((task) => (
                <TableRow
                  key={task.taskId}
                  className="cursor-pointer"
                  onClick={() => setSelected(task)}
                >
                  <TableCell className="truncate font-medium">
                    <Link
                      to={`/tasks/${encodeURIComponent(task.name)}`}
                      className="hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {task.name}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate">{task.taskId}</span>
                      <button
                        className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigator.clipboard.writeText(task.taskId);
                          setCopiedId(task.taskId);
                        }}
                      >
                        {copiedId === task.taskId ? (
                          <Check className="h-3.5 w-3.5 text-emerald-500" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </span>
                  </TableCell>
                  <TableCell className="truncate">{task.worker || "—"}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(task.status)}>
                      {task.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="truncate font-mono text-xs">
                    {task.runtime != null
                      ? `${task.runtime.toFixed(3)}s`
                      : "—"}
                  </TableCell>
                  <TableCell className="truncate text-xs text-muted-foreground">
                    {new Date(task.completedAt * 1000).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                {filtered.length} result{filtered.length !== 1 && "s"}
              </p>
              <Pagination>
                <PaginationContent>
                  <PaginationItem>
                    <PaginationPrevious
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className={currentPage <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                    />
                  </PaginationItem>
                  {getPageNumbers(currentPage, totalPages).map((p, i) =>
                    p === "ellipsis" ? (
                      <PaginationItem key={`e-${i}`}>
                        <PaginationEllipsis />
                      </PaginationItem>
                    ) : (
                      <PaginationItem key={p}>
                        <PaginationLink
                          isActive={p === currentPage}
                          onClick={() => setPage(p)}
                          className="cursor-pointer"
                        >
                          {p}
                        </PaginationLink>
                      </PaginationItem>
                    )
                  )}
                  <PaginationItem>
                    <PaginationNext
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      className={currentPage >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                    />
                  </PaginationItem>
                </PaginationContent>
              </Pagination>
            </div>
          )}
        </>
      )}

      {selected && (
        <TaskDetailDialog
          task={{
            taskId: selected.taskId,
            status: selected.status,
            result: selected.result ?? null,
            traceback: selected.traceback ?? null,
            dateDone: new Date(selected.completedAt * 1000).toISOString(),
            name: selected.name,
            worker: selected.worker,
            runtime: selected.runtime,
            args: selected.args,
            kwargs: selected.kwargs,
          }}
          open={!!selected}
          onOpenChange={(open) => !open && setSelected(null)}
        />
      )}
    </div>
  );
}
