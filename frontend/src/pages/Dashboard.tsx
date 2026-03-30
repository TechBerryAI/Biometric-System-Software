import { motion } from "framer-motion";
import { Clock, UserCheck, UserX, Users } from "lucide-react";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { AttendanceTrendChart } from "@/components/dashboard/AttendanceTrendChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useAttendanceTrend } from "@/hooks/useAttendanceTrend";
import { useDashboard } from "@/hooks/useDashboard";
import { useRecentLogs } from "@/hooks/useRecentLogs";
import { cn } from "@/lib/cn";
import type { DailySummaryRow } from "@/types";

function KpiCard({
  title,
  value,
  hint,
  icon: Icon,
  delay,
}: {
  title: string;
  value: string | number;
  hint: string;
  icon: typeof Users;
  delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
    >
      <Card className="group overflow-hidden transition-shadow duration-300 hover:shadow-card-hover">
        <CardContent className="p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">{title}</p>
              <p className="mt-3 font-display text-display-xl text-ink">{value}</p>
              <p className="mt-2 text-sm text-ink-muted leading-snug">{hint}</p>
            </div>
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary-soft text-primary transition-transform duration-300 group-hover:scale-105">
              <Icon className="h-5 w-5" strokeWidth={1.75} />
            </span>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function TodayTable({ rows }: { rows: DailySummaryRow[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-line/70 bg-surface-card shadow-card">
      <div className="scrollbar-thin overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="sticky top-0 z-[1] bg-surface/95 backdrop-blur-sm">
            <tr className="text-xs font-medium uppercase tracking-wider text-ink-muted shadow-[inset_0_-1px_0_#E2E8F0]">
              <th className="px-6 py-3.5">Name</th>
              <th className="px-6 py-3.5">Device ID</th>
              <th className="px-6 py-3.5">Punches</th>
              <th className="px-6 py-3.5">Work (min)</th>
              <th className="px-6 py-3.5">Late</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={row.employee_id}
                className={cn(
                  "border-b border-line/40 transition-colors duration-150 hover:bg-surface/80",
                  idx % 2 === 1 && "bg-surface/[0.35]"
                )}
              >
                <td className="px-6 py-3.5 font-medium text-ink">{row.employee_name}</td>
                <td className="px-6 py-3.5 font-mono text-xs text-ink-muted">{row.device_user_id}</td>
                <td className="px-6 py-3.5 tabular-nums text-ink-muted">{row.sessions_count}</td>
                <td className="px-6 py-3.5 tabular-nums text-ink-muted">
                  {row.total_work_minutes != null ? row.total_work_minutes : "—"}
                </td>
                <td className="px-6 py-3.5">
                  {row.late_arrival ? (
                    <Badge variant="late">Late</Badge>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Dashboard() {
  const dash = useDashboard();
  const trend = useAttendanceTrend(14);
  const activity = useRecentLogs(12);

  if (dash.loading) {
    return (
      <div className="space-y-8">
        <div>
          <Skeleton className="h-9 w-48" />
          <Skeleton className="mt-3 h-4 w-72" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
        <Skeleton className="h-[320px] w-full" />
      </div>
    );
  }

  if (dash.error) {
    return (
      <Card className="border-status-absent-soft bg-status-absent-soft/20">
        <CardContent className="p-8">
          <p className="text-sm font-medium text-status-absent">{dash.error}</p>
          <Button className="mt-4" onClick={() => void dash.reload()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-10">
      <header>
        <h1 className="font-display text-display-xl text-ink">Dashboard</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Today&apos;s operational snapshot from processed sessions and live punch trails — calm, precise, and ready
          for review.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Total employees"
          value={dash.totalEmployees}
          hint="Registered in the database"
          icon={Users}
          delay={0}
        />
        <KpiCard
          title="Present today"
          value={dash.presentToday}
          hint="At least one punch recorded"
          icon={UserCheck}
          delay={0.05}
        />
        <KpiCard
          title="Late arrivals"
          value={dash.lateCount}
          hint="After shift start (local)"
          icon={Clock}
          delay={0.1}
        />
        <KpiCard
          title="Absent"
          value={dash.absentToday}
          hint="No punches for the day"
          icon={UserX}
          delay={0.15}
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <AttendanceTrendChart data={trend.data} loading={trend.isLoading} />
        </div>
        <div className="lg:col-span-2">
          <ActivityFeed logs={activity.data} loading={activity.isLoading} />
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="font-display text-display-lg text-ink">Today by employee</h2>
          <p className="mt-1 text-sm text-ink-muted">Full roster with punch-derived metrics.</p>
        </div>
        {dash.summary.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center py-16 text-center">
              <p className="text-sm font-medium text-ink">No summary rows yet</p>
              <p className="mt-1 max-w-md text-sm text-ink-muted">
                Sync your device or verify that attendance exists for today in your timezone.
              </p>
            </CardContent>
          </Card>
        ) : (
          <TodayTable rows={dash.summary} />
        )}
      </section>
    </div>
  );
}
