import { motion } from "framer-motion";
import { Fingerprint } from "lucide-react";
import type { AttendanceLog } from "@/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { fmtDisplayDateTimeShort } from "@/lib/dates";

function fmtTime(iso: string): string {
  return fmtDisplayDateTimeShort(iso);
}

export function ActivityFeed({
  logs,
  loading,
}: {
  logs: AttendanceLog[] | undefined;
  loading: boolean;
}) {
  if (loading || !logs) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-36" />
          <Skeleton className="mt-2 h-4 w-52" />
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (logs.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>Latest punches pulled from your integration window.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-surface/50 px-6 py-14 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
              <Fingerprint className="h-6 w-6" strokeWidth={1.5} />
            </div>
            <p className="text-sm font-medium text-ink">No recent punches</p>
            <p className="mt-1 max-w-xs text-sm text-ink-muted">
              When devices sync, live punch events will appear here for quick review.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.05 }}>
      <Card className="border-line/60 bg-surface-card/95">
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>Latest punch events, kept compact for quick scan.</CardDescription>
        </CardHeader>
        <CardContent className="pt-2">
          <ul className="scrollbar-thin max-h-[360px] space-y-2 overflow-y-auto pr-1">
            {logs.map((log, idx) => (
              <motion.li
                key={log.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25, delay: idx * 0.03 }}
                className={cn(
                  "group flex items-center justify-between gap-3 rounded-xl border border-line/50 bg-surface/35 px-4 py-3",
                  "transition-all duration-200 hover:border-line hover:bg-surface-card hover:shadow-sm"
                )}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">
                    Device user <span className="font-mono text-xs text-primary">{log.employee_code}</span>
                  </p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    <span className="rounded-md bg-surface-card px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
                      {log.punch_type}
                    </span>
                    <span className="mx-1.5 text-ink-subtle">·</span>
                    {log.device_id}
                  </p>
                </div>
                <time className="shrink-0 text-xs tabular-nums text-ink-muted">{fmtTime(log.timestamp)}</time>
              </motion.li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </motion.div>
  );
}
