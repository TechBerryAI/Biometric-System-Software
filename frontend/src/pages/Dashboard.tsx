import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Percent, UserCheck, UserX, Users } from "lucide-react";
import { useMemo } from "react";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { AttendanceTrendChart } from "@/components/dashboard/AttendanceTrendChart";
import { DepartmentTodayBreakdown } from "@/components/dashboard/DepartmentTodayBreakdown";
import { ManagementInsightsCard } from "@/components/dashboard/ManagementInsightsCard";
import { WorkHoursTrendChart } from "@/components/dashboard/WorkHoursTrendChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttendanceTrend } from "@/hooks/useAttendanceTrend";
import { useDashboard } from "@/hooks/useDashboard";
import { useRecentLogs } from "@/hooks/useRecentLogs";
import {
  buildManagementInsights,
  computeTodayWorkStats,
  departmentTodayRollup,
  formatDecimalHours,
} from "@/lib/dashboardAnalytics";
import { fetchManagementInsights } from "@/services/api";

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
      <Card className="group overflow-hidden border-line/50 bg-surface-card/95 transition-shadow duration-300 hover:shadow-card-hover">
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

function CompactMetric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-xl border border-line/60 bg-surface/50 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold text-ink">{value}</p>
      <p className="mt-1 text-xs text-ink-muted">{hint}</p>
    </div>
  );
}

export function Dashboard() {
  const dash = useDashboard();
  const trend = useAttendanceTrend(14);
  const activity = useRecentLogs(8);

  const grokInsights = useQuery({
    queryKey: ["management-insights", 14],
    queryFn: () => fetchManagementInsights(14),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: !dash.loading && !dash.error,
  });

  const todayWork = useMemo(
    () =>
      computeTodayWorkStats(
        dash.summary,
        dash.totalEmployees,
        dash.presentToday
      ),
    [dash.summary, dash.totalEmployees, dash.presentToday]
  );

  const departmentRows = useMemo(
    () => departmentTodayRollup(dash.summary, dash.employees),
    [dash.summary, dash.employees]
  );

  const ruleInsightBullets = useMemo(
    () =>
      buildManagementInsights(
        trend.data ?? [],
        todayWork,
        dash.presentToday,
        dash.totalEmployees
      ),
    [trend.data, todayWork, dash.presentToday, dash.totalEmployees]
  );

  const insightBullets = useMemo(() => {
    const d = grokInsights.data;
    if (d?.available && d.source === "grok" && d.bullets.length > 0) {
      return d.bullets;
    }
    return ruleInsightBullets;
  }, [grokInsights.data, ruleInsightBullets]);

  const insightSource: "grok" | "rules" | "cache" | "error" | "unconfigured" = useMemo(() => {
    const d = grokInsights.data;
    if (d?.available && (d.source === "grok" || d.source === "cache") && d.bullets.length > 0) return d.source;
    if (d?.source === "error" || d?.source === "unconfigured") return d.source;
    return "rules";
  }, [grokInsights.data]);

  const insightCached = Boolean(grokInsights.data?.cached || grokInsights.data?.source === "cache");
  const insightErrorCode = grokInsights.data?.error_code ?? null;

  if (dash.loading) {
    return (
      <div className="space-y-8">
        <div>
          <Skeleton className="h-9 w-48" />
          <Skeleton className="mt-3 h-4 max-w-xl" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={`m-${i}`} className="h-32 w-full" />
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-5">
          <Skeleton className="h-[320px] w-full lg:col-span-3" />
          <Skeleton className="h-[320px] w-full lg:col-span-2" />
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-[340px] w-full" />
          <Skeleton className="h-[340px] w-full" />
        </div>
        <Skeleton className="h-40 w-full" />
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
    <div className="space-y-8">
      <header className="rounded-2xl border border-line/60 bg-gradient-to-r from-surface-card to-primary-soft/30 px-6 py-6 shadow-card">
        <h1 className="font-display text-display-xl text-ink">Dashboard</h1>
        <p className="mt-2 max-w-3xl text-sm text-ink-muted leading-relaxed">
          Headcount, attendance, and work hours in one view — built for quick management review and week-over-week context.
        </p>
        <p className="mt-3 text-xs font-medium uppercase tracking-wide text-ink-subtle">
          Today: {dash.presentToday}/{dash.totalEmployees} present
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
          title="Attendance rate"
          value={todayWork.attendanceRate != null ? `${todayWork.attendanceRate.toFixed(0)}%` : "—"}
          hint="Share of roster with a punch"
          icon={Percent}
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

      <section>
        <Card className="border-line/60 bg-surface-card/95">
          <CardContent className="space-y-4 p-5">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-ink">Operational snapshot</p>
              <p className="text-xs text-ink-muted">Simple daily health indicators</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <CompactMetric
                label="Attendance rate"
                value={todayWork.attendanceRate != null ? `${todayWork.attendanceRate.toFixed(0)}%` : "—"}
                hint="Share of roster with a punch"
              />
              <CompactMetric
                label="Avg hours"
                value={
                  todayWork.avgWorkMinutesAmongPresent != null
                    ? `${formatDecimalHours(todayWork.avgWorkMinutesAmongPresent)} h`
                    : "—"
                }
                hint="Among staff with checkout"
              />
              <CompactMetric
                label="Person-hours"
                value={
                  todayWork.totalWorkMinutes > 0
                    ? `${formatDecimalHours(todayWork.totalWorkMinutes)} h`
                    : "—"
                }
                hint="Total tracked work span"
              />
              <CompactMetric
                label="Absent today"
                value={`${dash.absentToday}`}
                hint="No punches recorded"
              />
            </div>
          </CardContent>
        </Card>
      </section>

      <ManagementInsightsCard
        bullets={insightBullets}
        source={insightSource}
        cached={insightCached}
        loading={grokInsights.isLoading}
        errorCode={insightErrorCode}
      />

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <AttendanceTrendChart data={trend.data} loading={trend.isLoading} />
        </div>
        <div className="lg:col-span-2">
          <ActivityFeed logs={activity.data} loading={activity.isLoading} />
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-1">
        <WorkHoursTrendChart data={trend.data} loading={trend.isLoading} />
      </section>

      <DepartmentTodayBreakdown rows={departmentRows} />
    </div>
  );
}
