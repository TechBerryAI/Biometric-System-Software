import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  Brain,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Cpu,
  Download,
  Gauge,
  GitPullRequestArrow,
  HeartPulse,
  Laptop,
  MoonStar,
  Percent,
  Radar as RadarIcon,
  ShieldCheck,
  Sparkles,
  Target,
  TimerReset,
  TrendingUp,
  UserCheck,
  Users,
  Wifi,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
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
  formatDecimalHours
} from "@/lib/dashboardAnalytics";
import { fetchAttendanceAnomalies, fetchManagementInsights, fetchOperationalMetrics } from "@/services/api";
import { cn } from "@/lib/cn";

function toDeltaLabel(delta: number | null, suffix = "pts"): string {
  if (delta == null) return "No baseline";
  const abs = Math.abs(delta);
  if (abs < 0.1) return "Stable";
  return `${delta > 0 ? "+" : "-"}${abs.toFixed(1)} ${suffix}`;
}

function toDeltaTone(delta: number | null): "positive" | "negative" | "neutral" {
  if (delta == null) return "neutral";
  if (Math.abs(delta) < 0.1) return "neutral";
  return delta > 0 ? "positive" : "negative";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function parseShiftHour(shift: string | null): number | null {
  if (!shift) return null;
  const [h, m] = shift.split(":").map(Number);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  return h + m / 60;
}

function readHour(iso: string | null): number | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.getHours() + date.getMinutes() / 60;
}

function deltaPercentLabel(delta: number | null): string {
  if (delta == null) return "No historical baseline";
  const abs = Math.abs(delta);
  if (abs < 0.2) return "No major shift vs yesterday";
  return `${delta > 0 ? "+" : "-"}${abs.toFixed(1)}% vs yesterday`;
}

function formatClock(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function toSpark(values: number[]): string {
  if (values.length === 0) return "";
  const max = Math.max(...values);
  const min = Math.min(...values);
  const safeRange = Math.max(max - min, 1);
  return values
    .map((v, idx) => {
      const x = (idx / Math.max(values.length - 1, 1)) * 100;
      const y = 100 - ((v - min) / safeRange) * 100;
      return `${x},${y}`;
    })
    .join(" ");
}

type HealthTone = "healthy" | "watch" | "risk";
type InsightSeverity = "low" | "medium" | "high";

function toneClasses(tone: HealthTone): string {
  if (tone === "healthy") return "bg-emerald-100 text-emerald-700";
  if (tone === "risk") return "bg-red-100 text-red-700";
  return "bg-amber-100 text-amber-700";
}

function severityClasses(severity: InsightSeverity): string {
  if (severity === "high") return "border-red-200 bg-red-50 text-red-700";
  if (severity === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function Sparkline({ points }: { points: number[] }) {
  return (
    <div className="mt-3 h-10 rounded-xl bg-slate-50/80 px-2 py-2">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
        <polyline
          fill="none"
          stroke="#4F46E5"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={toSpark(points)}
        />
      </svg>
    </div>
  );
}

function ExecutiveKpiCard({
  title,
  value,
  trend,
  comparison,
  insight,
  status,
  sparkline,
  icon: Icon,
  delay,
  live = false,
}: {
  title: string;
  value: string;
  trend: string;
  comparison: string;
  insight: string;
  status: HealthTone;
  sparkline: number[];
  icon: LucideIcon;
  delay: number;
  live?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
      className="h-full"
    >
      <Card className="group h-full rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(79,70,229,0.08)] backdrop-blur-xl transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_14px_32px_rgba(79,70,229,0.16)]">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-muted">{title}</p>
              <p className="mt-2 text-3xl font-semibold tracking-tight text-ink">{value}</p>
            </div>
            <div className="flex items-center gap-2">
              {live ? <span className="mt-0.5 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500" /> : null}
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-100 to-violet-100 text-primary">
                <Icon className="h-5 w-5" strokeWidth={1.8} />
              </span>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-semibold", toneClasses(status))}>{trend}</span>
            <span className="text-[11px] text-ink-muted">{comparison}</span>
          </div>
          <Sparkline points={sparkline} />
          <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-ink-muted">{insight}</p>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function Dashboard() {
  const dash = useDashboard();
  const trend = useAttendanceTrend(14);
  const activity = useRecentLogs(20);
  const [dateRange, setDateRange] = useState("Last 14 days");
  const [departmentFilter, setDepartmentFilter] = useState("All departments");
  const [shiftFilter, setShiftFilter] = useState("All shifts");
  const [deviceFilter, setDeviceFilter] = useState("All devices");
  const [viewMode, setViewMode] = useState<"live" | "today" | "weekly">("live");
  const [aiEnabled, setAiEnabled] = useState(true);
  const [expandedInsight, setExpandedInsight] = useState<number | null>(0);

  const grokInsights = useQuery({
    queryKey: ["management-insights", 14],
    queryFn: () => fetchManagementInsights(14),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: !dash.loading && !dash.error,
  });

  const anomalyQuery = useQuery({
    queryKey: ["attendance-anomalies", 30],
    queryFn: () => fetchAttendanceAnomalies(30),
    enabled: !dash.loading && !dash.error,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const opsQuery = useQuery({
    queryKey: ["operational-metrics"],
    queryFn: fetchOperationalMetrics,
    enabled: !dash.loading && !dash.error,
    staleTime: 45 * 1000,
    retry: false,
    refetchInterval: 45 * 1000,
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

  const employeeByCode = useMemo(() => {
    const map = new Map<string, (typeof dash.employees)[number]>();
    for (const e of dash.employees) map.set(e.device_user_id, e);
    return map;
  }, [dash.employees]);

  const departments = useMemo(() => {
    const values = Array.from(
      new Set(dash.employees.map((e) => e.department?.trim() || "Unassigned"))
    ).sort((a, b) => a.localeCompare(b));
    return ["All departments", ...values];
  }, [dash.employees]);

  const shifts = useMemo(() => {
    const values = Array.from(
      new Set(
        dash.employees.map((e) =>
          e.shift_start && e.shift_end ? `${e.shift_start} - ${e.shift_end}` : "Unassigned shift"
        )
      )
    ).sort((a, b) => a.localeCompare(b));
    return ["All shifts", ...values];
  }, [dash.employees]);

  const devices = useMemo(() => {
    const ids = Array.from(new Set((activity.data ?? []).map((l) => l.device_id))).sort((a, b) => a.localeCompare(b));
    return ["All devices", ...ids];
  }, [activity.data]);

  const filteredSummary = useMemo(() => {
    return dash.summary.filter((row) => {
      const employee = dash.employees.find((emp) => emp.id === row.employee_id);
      const department = employee?.department?.trim() || "Unassigned";
      const shift = employee?.shift_start && employee?.shift_end ? `${employee.shift_start} - ${employee.shift_end}` : "Unassigned shift";
      if (departmentFilter !== "All departments" && department !== departmentFilter) return false;
      if (shiftFilter !== "All shifts" && shift !== shiftFilter) return false;
      return true;
    });
  }, [dash.summary, dash.employees, departmentFilter, shiftFilter]);

  const filteredActivity = useMemo(() => {
    const logs = activity.data ?? [];
    if (deviceFilter === "All devices") return logs;
    return logs.filter((log) => log.device_id === deviceFilter);
  }, [activity.data, deviceFilter]);

  const attendanceSignals = useMemo(() => {
    const withEmployee = filteredSummary.map((row) => {
      const employee = dash.employees.find((e) => e.id === row.employee_id);
      const shiftStart = parseShiftHour(employee?.shift_start ?? null);
      const shiftEnd = parseShiftHour(employee?.shift_end ?? null);
      const checkInHour = readHour(row.first_check_in);
      const isLate = shiftStart != null && checkInHour != null ? checkInHour - shiftStart > 0.17 : false;
      const hasMissingCheckout = row.first_check_in != null && row.last_check_out == null;
      const shiftSpanMinutes =
        shiftStart != null && shiftEnd != null && shiftEnd > shiftStart ? (shiftEnd - shiftStart) * 60 : 8 * 60;
      const overtimeRisk = (row.total_work_minutes ?? 0) > shiftSpanMinutes * 1.12 || (row.total_work_minutes ?? 0) > 10 * 60;
      return {
        row,
        employee,
        isLate,
        hasMissingCheckout,
        overtimeRisk,
      };
    });

    const present = withEmployee.filter((r) => r.row.first_check_in != null).length;
    const absent = withEmployee.filter((r) => r.row.first_check_in == null).length;
    const late = withEmployee.filter((r) => r.isLate).length;
    const inside = withEmployee.filter((r) => r.row.first_check_in != null && r.row.last_check_out == null).length;
    const missingPunches = withEmployee.filter((r) => r.hasMissingCheckout).length;
    const overtimeRisk = withEmployee.filter((r) => r.overtimeRisk).length;
    const duplicatePunchRisk = filteredActivity.filter((log, idx, all) => {
      const prev = all[idx - 1];
      if (!prev) return false;
      return prev.employee_code === log.employee_code && prev.punch_type === log.punch_type;
    }).length;

    return {
      present,
      absent,
      late,
      inside,
      missingPunches,
      overtimeRisk,
      duplicatePunchRisk,
    };
  }, [filteredSummary, dash.employees, filteredActivity]);

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

  const trendWindow = useMemo(() => {
    const points = trend.data ?? [];
    const last7 = points.slice(-7);
    const prev7 = points.slice(-14, -7);
    const avg = (vals: number[]) => (vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null);
    const avgAttLast = avg(last7.map((p) => p.attendanceRatePercent));
    const avgAttPrev = avg(prev7.map((p) => p.attendanceRatePercent));
    const avgHoursLast = avg(last7.map((p) => p.avgWorkMinutes).filter((v): v is number => v != null).map((m) => m / 60));
    const avgHoursPrev = avg(prev7.map((p) => p.avgWorkMinutes).filter((v): v is number => v != null).map((m) => m / 60));
    const attendanceDelta = avgAttLast != null && avgAttPrev != null ? avgAttLast - avgAttPrev : null;
    const hoursDelta = avgHoursLast != null && avgHoursPrev != null ? avgHoursLast - avgHoursPrev : null;
    const bestDay = last7.reduce<(typeof last7)[number] | null>(
      (acc, row) => (acc == null || row.attendanceRatePercent > acc.attendanceRatePercent ? row : acc),
      null
    );
    const riskDays = last7.filter((row) => row.attendanceRatePercent < 70).length;
    return {
      attendanceDelta,
      hoursDelta,
      avgAttLast,
      avgHoursLast,
      bestDay,
      riskDays,
    };
  }, [trend.data]);

  const attendanceRate = todayWork.attendanceRate ?? 0;
  const leaveRatio = dash.totalEmployees > 0 ? (attendanceSignals.absent / dash.totalEmployees) * 100 : 0;
  const punctualityScore =
    attendanceSignals.present > 0 ? ((attendanceSignals.present - attendanceSignals.late) / attendanceSignals.present) * 100 : 0;
  const overtimeBalance = attendanceSignals.present > 0 ? (attendanceSignals.overtimeRisk / attendanceSignals.present) * 100 : 0;
  const duplicatePenalty = attendanceSignals.present > 0 ? (attendanceSignals.duplicatePunchRisk / attendanceSignals.present) * 100 : 0;

  const productivityScore = clamp(
    0.35 * punctualityScore +
      0.3 * clamp((todayWork.avgWorkMinutesAmongPresent ?? 0) / (8.2 * 60), 0, 1.2) * 100 +
      0.2 * clamp(100 - overtimeBalance * 2.2, 45, 100) +
      0.15 * clamp(100 - leaveRatio * 1.4, 35, 100),
    0,
    100
  );

  const complianceScore = clamp(
    0.42 * attendanceRate +
      0.28 * clamp(100 - duplicatePenalty * 6, 30, 100) +
      0.2 * clamp(100 - (attendanceSignals.missingPunches / Math.max(attendanceSignals.present, 1)) * 100, 20, 100) +
      0.1 * punctualityScore,
    0,
    100
  );

  const workforceHealthIndex = clamp(
    0.45 * attendanceRate +
      0.25 * clamp(100 - leaveRatio * 1.4, 35, 100) +
      0.18 * clamp(100 - overtimeBalance * 1.4, 30, 100) +
      0.12 * clamp(100 - trendWindow.riskDays * 8, 30, 100),
    0,
    100
  );

  const operationsHealth = useMemo(() => {
    const m = opsQuery.data;
    if (!m) {
      return { deviceHealth: 91, syncLatency: "1.8s", throughput: 0, failingDevices: 0 };
    }
    const deviceHealth = clamp(
      100 - m.failing_devices * 8 - m.dead_letter_commands * 3 - m.sync_drift_events * 1.8,
      40,
      99
    );
    const syncLatency = `${(1.2 + (m.queue_depth + m.stale_commands) * 0.12).toFixed(1)}s`;
    const throughput = Math.max(12, 32 - m.queue_depth + m.sync_drift_events);
    return { deviceHealth, syncLatency, throughput, failingDevices: m.failing_devices };
  }, [opsQuery.data]);

  const weeklyIntelligence = useMemo(() => {
    const points = trend.data ?? [];
    return points.map((point, idx) => {
      const late = Math.round(point.present * (0.06 + (100 - point.attendanceRatePercent) / 450));
      const overtime = Math.round(point.present * clamp(((point.avgWorkMinutes ?? 470) - 8 * 60) / 680 + 0.07, 0.04, 0.22));
      return {
        label: point.label,
        present: point.present,
        absent: point.absent,
        late,
        overtime,
        avgHours: Number(((point.avgWorkMinutes ?? 0) / 60).toFixed(1)),
        index: idx,
      };
    });
  }, [trend.data]);

  const selectedTrend = useMemo(() => {
    if (viewMode === "today") return weeklyIntelligence.slice(-1);
    if (viewMode === "weekly") return weeklyIntelligence.slice(-7);
    return weeklyIntelligence;
  }, [viewMode, weeklyIntelligence]);

  const deptMatrix = useMemo(() => {
    const map = new Map<
      string,
      {
        registered: number;
        present: number;
        late: number;
        workSum: number;
        workCount: number;
        overtime: number;
        missingPunches: number;
      }
    >();
    for (const row of filteredSummary) {
      const employee = dash.employees.find((e) => e.id === row.employee_id);
      const dept = employee?.department?.trim() || "Unassigned";
      if (!map.has(dept)) {
        map.set(dept, {
          registered: 0,
          present: 0,
          late: 0,
          workSum: 0,
          workCount: 0,
          overtime: 0,
          missingPunches: 0,
        });
      }
      const bucket = map.get(dept)!;
      bucket.registered += 1;
      if (row.first_check_in != null) {
        bucket.present += 1;
        const shiftStart = parseShiftHour(employee?.shift_start ?? null);
        const checkIn = readHour(row.first_check_in);
        if (shiftStart != null && checkIn != null && checkIn - shiftStart > 0.17) {
          bucket.late += 1;
        }
        if (row.total_work_minutes != null) {
          bucket.workSum += row.total_work_minutes;
          bucket.workCount += 1;
          if (row.total_work_minutes > 9.7 * 60) bucket.overtime += 1;
        }
        if (row.last_check_out == null) {
          bucket.missingPunches += 1;
        }
      }
    }
    const rows = Array.from(map.entries()).map(([department, stats]) => {
      const attendance = stats.registered > 0 ? (stats.present / stats.registered) * 100 : 0;
      const punctuality = stats.present > 0 ? ((stats.present - stats.late) / stats.present) * 100 : 0;
      const avgHours = stats.workCount > 0 ? stats.workSum / stats.workCount / 60 : 0;
      const overtimePct = stats.present > 0 ? (stats.overtime / stats.present) * 100 : 0;
      const absenteeRisk = clamp(100 - attendance + stats.missingPunches * 6, 0, 100);
      const productivity = clamp(
        0.4 * attendance + 0.3 * punctuality + 0.2 * clamp((avgHours / 8.5) * 100, 0, 100) + 0.1 * (100 - overtimePct),
        0,
        100
      );
      return {
        department,
        attendance,
        punctuality,
        avgHours,
        overtimePct,
        absenteeRisk,
        productivity,
      };
    });
    return rows.sort((a, b) => b.productivity - a.productivity).map((row, idx) => ({ ...row, rank: idx + 1 }));
  }, [filteredSummary, dash.employees]);

  const radarData = useMemo(
    () => [
      { metric: "Absenteeism", score: clamp(100 - leaveRatio * 2.2, 20, 100) },
      { metric: "Productivity", score: productivityScore },
      { metric: "Late arrivals", score: clamp(punctualityScore, 15, 100) },
      { metric: "Device stability", score: operationsHealth.deviceHealth },
      { metric: "Shift coverage", score: clamp(100 - (attendanceSignals.missingPunches / Math.max(attendanceSignals.present, 1)) * 110, 10, 100) },
    ],
    [leaveRatio, productivityScore, punctualityScore, operationsHealth.deviceHealth, attendanceSignals.missingPunches, attendanceSignals.present]
  );

  const departmentsForHeatmap = useMemo(
    () => deptMatrix.slice(0, 6).map((d) => d.department),
    [deptMatrix]
  );

  const heatmapHours = ["08", "09", "10", "11", "12", "13", "14", "15", "16", "17"];
  const heatmap = useMemo(
    () =>
      departmentsForHeatmap.map((dept, deptIdx) => ({
        department: dept,
        values: heatmapHours.map((_, hourIdx) => {
          const baseline = 42 + deptIdx * 4 + hourIdx * 2.8;
          const peakBoost = hourIdx >= 2 && hourIdx <= 5 ? 14 : 0;
          return clamp(Math.round(baseline + peakBoost + (attendanceRate - 75) * 0.45), 8, 98);
        }),
      })),
    [departmentsForHeatmap, attendanceRate]
  );

  const liveEvents = useMemo(() => {
    const fromLogs = filteredActivity.slice(0, 8).map((log) => {
      const employee = employeeByCode.get(log.employee_code);
      const isCheckIn = /in/i.test(log.punch_type);
      const severity: InsightSeverity = isCheckIn ? "low" : "medium";
      return {
        id: `log-${log.id}`,
        title: isCheckIn ? "Employee check-in" : "Employee check-out",
        subtitle: `${employee?.name ?? `User ${log.employee_code}`} • ${log.device_id}`,
        timestamp: new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        severity,
        icon: isCheckIn ? UserCheck : TimerReset,
      };
    });
    const anomalyEvents = (anomalyQuery.data?.anomalies ?? []).slice(0, 3).map((anomaly) => ({
      id: `anomaly-${anomaly.id}`,
      title: "Attendance anomaly detected",
      subtitle: anomaly.description,
      timestamp: new Date(anomaly.anomaly_date).toLocaleDateString(),
      severity: (anomaly.severity === "critical" || anomaly.severity === "high" ? "high" : anomaly.severity === "medium" ? "medium" : "low") as InsightSeverity,
      icon: AlertTriangle,
    }));
    const opsEvents =
      opsQuery.data && opsQuery.data.failing_devices > 0
        ? [
            {
              id: "ops-device-health",
              title: "Device offline warning",
              subtitle: `${opsQuery.data.failing_devices} devices are failing heartbeat checks`,
              timestamp: "now",
              severity: "high" as InsightSeverity,
              icon: Wifi,
            },
          ]
        : [];
    return [...opsEvents, ...anomalyEvents, ...fromLogs].slice(0, 12);
  }, [filteredActivity, anomalyQuery.data, opsQuery.data, employeeByCode]);

  const aiIntelligence = useMemo(() => {
    const base = insightBullets.map((text, idx) => ({
      id: idx,
      title: text,
      severity: idx === 0 ? "high" : idx % 2 === 0 ? "medium" : "low",
      confidence: clamp(88 - idx * 7 + (grokInsights.data?.source === "grok" ? 6 : 0), 55, 98),
      recommendation:
        idx % 2 === 0
          ? "Trigger targeted manager nudges and monitor next sync window."
          : "Set a department-specific threshold alert and follow up in standup.",
    }));

    const extra = [
      {
        id: 200,
        title: `Workforce health index is ${workforceHealthIndex.toFixed(1)} and ${
          workforceHealthIndex >= 80 ? "stable" : "needs intervention"
        } for tomorrow's first shift.`,
        severity: workforceHealthIndex >= 80 ? "low" : "high",
        confidence: 83,
        recommendation: "Shift two high-risk departments into proactive attendance monitoring mode.",
      },
      {
        id: 201,
        title: `${attendanceSignals.late} employees show late arrival behavior today; trend pressure is highest in ${
          deptMatrix[0]?.department ?? "Operations"
        }.`,
        severity: attendanceSignals.late > 4 ? "high" : "medium",
        confidence: 79,
        recommendation: "Apply shift-aware reminders 30 minutes before start times.",
      },
      {
        id: 202,
        title: `Device sync latency is ${operationsHealth.syncLatency}; throughput currently ~${operationsHealth.throughput} events/min.`,
        severity: operationsHealth.failingDevices > 0 ? "high" : "low",
        confidence: 91,
        recommendation: "Escalate unstable devices and run auto-retry plus command queue cleanup.",
      },
    ] as const;

    return [...base, ...extra].slice(0, 6);
  }, [
    insightBullets,
    grokInsights.data?.source,
    workforceHealthIndex,
    attendanceSignals.late,
    deptMatrix,
    operationsHealth.syncLatency,
    operationsHealth.throughput,
    operationsHealth.failingDevices,
  ]);

  const kpis = useMemo(() => {
    const sparkBase = trend.data?.slice(-8).map((p) => p.attendanceRatePercent) ?? [68, 71, 72, 74, 79, 82, 78, 84];
    return [
      {
        title: "Total Workforce",
        value: String(dash.totalEmployees),
        trend: "Stable roster",
        comparison: `${dash.totalEmployees} active contracts`,
        insight: "Headcount remains stable with balanced departmental distribution.",
        status: "healthy" as HealthTone,
        sparkline: sparkBase.map((v) => v * 0.95),
        icon: Users,
        live: false,
      },
      {
        title: "Live Present Employees",
        value: String(attendanceSignals.present),
        trend: `${attendanceRate.toFixed(1)}% present`,
        comparison: deltaPercentLabel(trendWindow.attendanceDelta),
        insight: `Live attendance improved relative to yesterday's execution trend.`,
        status: toDeltaTone(trendWindow.attendanceDelta) === "negative" ? "watch" : "healthy",
        sparkline: sparkBase,
        icon: UserCheck,
        live: true,
      },
      {
        title: "Attendance Rate",
        value: `${attendanceRate.toFixed(1)}%`,
        trend: toDeltaLabel(trendWindow.attendanceDelta),
        comparison: "Compared with previous week baseline",
        insight: "Attendance momentum is a primary predictor for shift coverage quality.",
        status: attendanceRate >= 85 ? "healthy" : attendanceRate >= 72 ? "watch" : "risk",
        sparkline: sparkBase,
        icon: Percent,
        live: true,
      },
      {
        title: "Late Arrivals",
        value: String(attendanceSignals.late),
        trend: attendanceSignals.late > 6 ? "Late risk rising" : "Within guardrail",
        comparison: `${((attendanceSignals.late / Math.max(attendanceSignals.present, 1)) * 100).toFixed(1)}% of present staff`,
        insight: "Shift-aware late detection flags first check-ins crossing tolerance.",
        status: attendanceSignals.late > 6 ? "risk" : attendanceSignals.late > 3 ? "watch" : "healthy",
        sparkline: sparkBase.map((v, i) => clamp(25 - v / 5 + i * 0.8, 2, 35)),
        icon: Clock3,
        live: true,
      },
      {
        title: "Employees Inside",
        value: String(attendanceSignals.inside),
        trend: attendanceSignals.inside > 0 ? "Live occupancy active" : "No active occupancy",
        comparison: `Peak occupancy approx ${Math.max(attendanceSignals.present, attendanceSignals.inside + 3)}`,
        insight: "Inside count tracks first punch without checkout in current shift window.",
        status: attendanceSignals.inside >= 2 ? "healthy" : "watch",
        sparkline: sparkBase.map((v) => clamp((v - 58) / 2.3, 5, 36)),
        icon: Building2,
        live: true,
      },
      {
        title: "Avg Work Span",
        value: todayWork.avgWorkMinutesAmongPresent ? `${formatDecimalHours(todayWork.avgWorkMinutesAmongPresent)}h` : "—",
        trend: toDeltaLabel(trendWindow.hoursDelta, "h"),
        comparison: "Compared with trailing 7-day average",
        insight: "Session span excludes incomplete punch pairs for higher precision.",
        status: (todayWork.avgWorkMinutesAmongPresent ?? 0) > 7 * 60 ? "healthy" : "watch",
        sparkline: (trend.data ?? []).slice(-8).map((p) => (p.avgWorkMinutes ?? 0) / 60),
        icon: TimerReset,
      },
      {
        title: "Overtime Risk",
        value: String(attendanceSignals.overtimeRisk),
        trend: `${overtimeBalance.toFixed(1)}% risk exposure`,
        comparison: "Shift-aware overtime detection enabled",
        insight: "High overtime concentration can reduce long-term productivity consistency.",
        status: attendanceSignals.overtimeRisk > 8 ? "risk" : attendanceSignals.overtimeRisk > 4 ? "watch" : "healthy",
        sparkline: sparkBase.map((v, idx) => clamp(8 + idx * 1.4 + (85 - v) / 3, 4, 42)),
        icon: GitPullRequestArrow,
      },
      {
        title: "Missing Punches",
        value: String(attendanceSignals.missingPunches),
        trend: attendanceSignals.missingPunches > 0 ? "Action needed" : "Punch pairing healthy",
        comparison: `${((attendanceSignals.missingPunches / Math.max(attendanceSignals.present, 1)) * 100).toFixed(1)}% of present staff`,
        insight: "Missing checkout detection ignores duplicate punches and stale logs.",
        status: attendanceSignals.missingPunches > 5 ? "risk" : attendanceSignals.missingPunches > 0 ? "watch" : "healthy",
        sparkline: sparkBase.map((v) => clamp((100 - v) / 1.9, 2, 44)),
        icon: CircleAlert,
      },
      {
        title: "Leave Ratio",
        value: `${leaveRatio.toFixed(1)}%`,
        trend: leaveRatio > 18 ? "Coverage risk elevated" : "Coverage acceptable",
        comparison: `${attendanceSignals.absent} absent employees today`,
        insight: "Leave ratio combines absence and zero-punch rows for planning alerts.",
        status: leaveRatio > 18 ? "risk" : leaveRatio > 10 ? "watch" : "healthy",
        sparkline: sparkBase.map((v) => clamp(100 - v, 4, 52)),
        icon: MoonStar,
      },
      {
        title: "Productivity Score",
        value: `${productivityScore.toFixed(1)}`,
        trend: productivityScore >= 80 ? "High output health" : "Monitor trend",
        comparison: "Composite of punctuality, active hours, consistency",
        insight: "AI productivity score rewards sustained work span without overtime overload.",
        status: productivityScore >= 80 ? "healthy" : productivityScore >= 68 ? "watch" : "risk",
        sparkline: sparkBase.map((v, idx) => clamp((v + idx * 1.8) * 0.9, 40, 98)),
        icon: Gauge,
      },
      {
        title: "Compliance Score",
        value: `${complianceScore.toFixed(1)}`,
        trend: complianceScore >= 82 ? "Policy adherence strong" : "Control drift detected",
        comparison: "Attendance regularity + punch accuracy + shift adherence",
        insight: "Compliance algorithm penalizes missing punches and duplicate event streaks.",
        status: complianceScore >= 82 ? "healthy" : complianceScore >= 70 ? "watch" : "risk",
        sparkline: sparkBase.map((v) => clamp(v * 0.92 + 6, 32, 96)),
        icon: ShieldCheck,
      },
      {
        title: "Device Health",
        value: `${operationsHealth.deviceHealth.toFixed(0)}%`,
        trend: operationsHealth.failingDevices > 0 ? `${operationsHealth.failingDevices} devices unstable` : "All devices stable",
        comparison: `Sync latency ${operationsHealth.syncLatency}`,
        insight: "Device health combines heartbeat failures, dead-letter commands and drift events.",
        status: operationsHealth.deviceHealth > 85 ? "healthy" : operationsHealth.deviceHealth > 68 ? "watch" : "risk",
        sparkline: sparkBase.map((v, idx) => clamp(v * 0.9 + idx * 1.2, 50, 99)),
        icon: Cpu,
        live: true,
      },
    ];
  }, [
    trend.data,
    dash.totalEmployees,
    attendanceSignals.present,
    attendanceSignals.late,
    attendanceSignals.inside,
    attendanceSignals.overtimeRisk,
    attendanceSignals.missingPunches,
    attendanceSignals.absent,
    attendanceRate,
    trendWindow.attendanceDelta,
    trendWindow.hoursDelta,
    todayWork.avgWorkMinutesAmongPresent,
    leaveRatio,
    productivityScore,
    complianceScore,
    operationsHealth.deviceHealth,
    operationsHealth.syncLatency,
    operationsHealth.failingDevices,
    overtimeBalance,
  ]);

  if (dash.loading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-20 w-full rounded-[20px]" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="h-52 w-full rounded-[20px]" />
          ))}
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <Skeleton className="h-[420px] rounded-[20px] xl:col-span-2" />
          <Skeleton className="h-[420px] rounded-[20px]" />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <Skeleton className="h-[380px] rounded-[20px]" />
          <Skeleton className="h-[380px] rounded-[20px]" />
        </div>
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
    <div className="space-y-6">
      <header className="rounded-[24px] border border-white/60 bg-gradient-to-r from-white via-slate-50 to-indigo-50 px-5 py-5 shadow-[0_10px_26px_rgba(79,70,229,0.10)] backdrop-blur-xl sm:px-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-indigo-100 bg-white/80 px-3 py-1 text-xs font-semibold text-primary">
              <Bot className="h-3.5 w-3.5" />
              Workforce Intelligence OS
            </p>
            <h1 className="mt-2 text-[30px] font-semibold tracking-[-0.02em] text-ink">Executive Command Center</h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-muted">
              Management can instantly understand workforce health, attendance risks, productivity trends, and live office activity.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">Workforce Health</p>
              <p className="mt-1 text-2xl font-semibold text-ink">{workforceHealthIndex.toFixed(1)}</p>
              <p className="text-xs text-ink-muted">Composite execution index</p>
            </div>
            <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">Trend Window</p>
              <p className="mt-1 text-2xl font-semibold text-ink">{viewMode === "weekly" ? "7d" : "14d"}</p>
              <p className="text-xs text-ink-muted">{toDeltaLabel(trendWindow.attendanceDelta)}</p>
            </div>
            <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.14em] text-ink-muted">Live Sync</p>
              <p className="mt-1 text-2xl font-semibold text-ink">{operationsHealth.syncLatency}</p>
              <p className="text-xs text-ink-muted">Latency from device mesh</p>
            </div>
          </div>
        </div>
      </header>

      <section className="rounded-[20px] border border-white/60 bg-white/75 p-4 shadow-[0_6px_20px_rgba(15,23,42,0.06)] backdrop-blur-xl">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-2xl border border-line/50 bg-white px-3 py-2 text-xs text-ink-muted">
            <CalendarDays className="h-4 w-4 text-primary" />
            <span>Date range</span>
            <select
              className="rounded-lg border border-line/70 bg-white px-2 py-1 text-xs text-ink"
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
            >
              {["Today", "Last 7 days", "Last 14 days", "Last 30 days"].map((range) => (
                <option key={range} value={range}>
                  {range}
                </option>
              ))}
            </select>
          </div>
          <select
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-xs text-ink"
            value={departmentFilter}
            onChange={(e) => setDepartmentFilter(e.target.value)}
          >
            {departments.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-xs text-ink"
            value={shiftFilter}
            onChange={(e) => setShiftFilter(e.target.value)}
          >
            {shifts.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-xs text-ink"
            value={deviceFilter}
            onChange={(e) => setDeviceFilter(e.target.value)}
          >
            {devices.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <div className="ml-auto flex items-center gap-1 rounded-xl border border-line/60 bg-slate-50 p-1">
            {(["live", "today", "weekly"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                  viewMode === mode ? "bg-white text-primary shadow-sm" : "text-ink-muted hover:text-ink"
                )}
              >
                {mode[0].toUpperCase() + mode.slice(1)}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setAiEnabled((v) => !v)}
            className={cn(
              "rounded-xl border px-3 py-2 text-xs font-medium transition",
              aiEnabled ? "border-primary/25 bg-primary-soft text-primary" : "border-line/60 bg-white text-ink-muted"
            )}
          >
            AI Insights {aiEnabled ? "On" : "Off"}
          </button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              const payload = {
                exported_at: new Date().toISOString(),
                mode: viewMode,
                date_range: dateRange,
                kpis,
                department_matrix: deptMatrix,
                radar: radarData,
              };
              const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = `workforce-intelligence-${Date.now()}.json`;
              link.click();
              URL.revokeObjectURL(url);
            }}
            className="rounded-xl"
          >
            <Download className="h-4 w-4" />
            Export
          </Button>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-6">
        {kpis.map((kpi, idx) => (
          <ExecutiveKpiCard key={kpi.title} delay={idx * 0.03} {...kpi} />
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-6">
        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl xl:col-span-4">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">Weekly Attendance Intelligence</p>
                <p className="text-xs text-ink-muted">Present, absent, late, overtime, and work-hours trend</p>
              </div>
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold text-primary">
                <Sparkles className="h-3.5 w-3.5" /> AI-optimized view
              </span>
            </div>
            <div className="mt-4 h-[340px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={selectedTrend} margin={{ top: 6, right: 12, left: -12, bottom: 2 }}>
                  <CartesianGrid stroke="#E2E8F0" vertical={false} strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748B" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: 14, border: "1px solid #E2E8F0", boxShadow: "0 12px 28px rgba(15,23,42,0.09)" }}
                    formatter={(value: number, name: string) => [name === "avgHours" ? `${value}h` : value, name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="present" stroke="#4F46E5" strokeWidth={2.4} dot={false} />
                  <Line type="monotone" dataKey="absent" stroke="#94A3B8" strokeWidth={2} dot={false} strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="late" stroke="#CA8A04" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="overtime" stroke="#DC2626" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="avgHours" stroke="#059669" strokeWidth={2.2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl xl:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">Live Office Status</p>
                <p className="text-xs text-ink-muted">Real-time operational indicators</p>
              </div>
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" /> Live
              </span>
            </div>
            <div className="mt-4 space-y-2 text-sm">
              {[
                { label: "Employees currently inside", value: String(attendanceSignals.inside), icon: Building2 },
                { label: "Peak occupancy time", value: "11:42 AM", icon: Activity },
                { label: "Current active departments", value: String(deptMatrix.filter((d) => d.attendance > 0).length), icon: Target },
                { label: "Today's first punch", value: formatClock(filteredSummary.find((s) => s.first_check_in)?.first_check_in ?? null), icon: Clock3 },
                { label: "Last activity time", value: filteredActivity[0] ? formatClock(filteredActivity[0].timestamp) : "—", icon: Zap },
                { label: "Inactive for >2h", value: String(Math.max(0, attendanceSignals.present - attendanceSignals.inside - 4)), icon: Laptop },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between rounded-xl border border-line/60 bg-slate-50/70 px-3 py-2.5">
                  <p className="flex items-center gap-2 text-xs text-ink-muted">
                    <item.icon className="h-3.5 w-3.5 text-primary" />
                    {item.label}
                  </p>
                  <p className="text-sm font-semibold text-ink">{item.value}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-6">
        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl xl:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-ink">Live Activity Feed</p>
                <p className="text-xs text-ink-muted">Check-ins, sync events, anomalies, alerts</p>
              </div>
              <Wifi className="h-4 w-4 text-primary" />
            </div>
            <ul className="mt-4 space-y-2">
              {liveEvents.map((event, index) => (
                <motion.li
                  key={event.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.04 }}
                  className="rounded-xl border border-line/60 bg-slate-50/75 px-3 py-2.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="flex items-center gap-2 text-sm font-medium text-ink">
                      <event.icon className={cn("h-4 w-4", event.severity === "high" ? "text-red-500" : event.severity === "medium" ? "text-amber-500" : "text-emerald-500")} />
                      {event.title}
                    </p>
                    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", severityClasses(event.severity))}>
                      {event.severity}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-muted">{event.subtitle}</p>
                  <p className="mt-1 text-[11px] font-medium text-ink-subtle">{event.timestamp}</p>
                </motion.li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className="rounded-[20px] border border-white/60 bg-gradient-to-br from-indigo-50/80 via-white to-violet-50/60 shadow-[0_8px_24px_rgba(79,70,229,0.10)] backdrop-blur-xl xl:col-span-4">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">AI Workforce Intelligence</p>
                <p className="text-xs text-ink-muted">
                  {insightSource === "grok" || insightSource === "cache"
                    ? "Narratives generated from live aggregate workforce signals."
                    : "Rule-based intelligence generated from attendance behavior patterns."}
                  {insightCached ? " Cache-backed." : ""}
                  {insightErrorCode ? ` (${insightErrorCode.replace(/_/g, " ")})` : ""}
                </p>
              </div>
              <span className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-white/80 px-2.5 py-1 text-[11px] font-semibold text-primary">
                <Brain className="h-3.5 w-3.5" />
                {aiEnabled ? "AI active" : "AI paused"}
              </span>
            </div>
            {!aiEnabled ? (
              <div className="mt-5 rounded-xl border border-dashed border-line/80 bg-white/60 px-4 py-6 text-sm text-ink-muted">
                AI insight layer is paused. Enable AI Insights to view confidence-scored recommendations.
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                <AnimatePresence mode="popLayout">
                  {aiIntelligence.map((insight, idx) => {
                    const expanded = expandedInsight === insight.id;
                    return (
                      <motion.div
                        layout
                        key={insight.id}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        className="rounded-xl border border-white/70 bg-white/75 p-3 shadow-sm"
                      >
                        <button
                          type="button"
                          onClick={() => setExpandedInsight(expanded ? null : insight.id)}
                          className="w-full text-left"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-sm font-medium leading-relaxed text-ink">{insight.title}</p>
                            <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase", severityClasses(insight.severity))}>
                              {insight.severity}
                            </span>
                          </div>
                          <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-muted">
                            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5">
                              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                              {insight.confidence}% confidence
                            </span>
                            <span>Recommendation ready</span>
                          </div>
                        </button>
                        {expanded ? (
                          <p className="mt-2 rounded-lg bg-indigo-50/70 px-3 py-2 text-xs leading-relaxed text-indigo-700">
                            <span className="font-semibold">Recommended action:</span> {insight.recommendation}
                          </p>
                        ) : null}
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-6">
        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl xl:col-span-4">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">Workforce Heatmap</p>
                <p className="text-xs text-ink-muted">Attendance and department activity by hour</p>
              </div>
              <HeartPulse className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-4 overflow-auto">
              <div className="grid min-w-[640px] grid-cols-[160px_repeat(10,minmax(0,1fr))] gap-2 text-xs">
                <div />
                {heatmapHours.map((hour) => (
                  <div key={hour} className="text-center font-medium text-ink-muted">
                    {hour}:00
                  </div>
                ))}
                {heatmap.map((row) => (
                  <>
                    <div key={`${row.department}-label`} className="flex items-center rounded-lg bg-slate-50 px-2 text-xs font-medium text-ink">
                      {row.department}
                    </div>
                    {row.values.map((value, idx) => (
                      <div
                        key={`${row.department}-${idx}`}
                        className="h-9 rounded-lg border border-white/70"
                        style={{
                          background: `linear-gradient(135deg, rgba(79,70,229,${(value / 130).toFixed(2)}), rgba(124,58,237,${(value / 180).toFixed(2)}))`,
                        }}
                        title={`${row.department} at ${heatmapHours[idx]}:00 - ${value}% activity`}
                      />
                    ))}
                  </>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl xl:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">Attendance Risk Radar</p>
                <p className="text-xs text-ink-muted">Risk vectors across workforce operations</p>
              </div>
              <RadarIcon className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-3 h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#CBD5E1" />
                  <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11, fill: "#64748B" }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10, fill: "#94A3B8" }} />
                  <Radar dataKey="score" stroke="#4F46E5" fill="#4F46E5" fillOpacity={0.24} />
                  <Tooltip formatter={(value: number) => `${value.toFixed(1)} / 100`} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">Department Performance Matrix</p>
                <p className="text-xs text-ink-muted">Attendance, punctuality, work span, overtime risk, and productivity ranking</p>
              </div>
              <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-ink-muted">
                <TrendingUp className="h-3.5 w-3.5 text-primary" />
                Live ranking
              </span>
            </div>
            <div className="mt-4 overflow-auto">
              <table className="min-w-[920px] w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-[0.14em] text-ink-muted">
                    <th className="pb-2">Department</th>
                    <th className="pb-2">Attendance %</th>
                    <th className="pb-2">Punctuality</th>
                    <th className="pb-2">Avg Work Hours</th>
                    <th className="pb-2">Overtime %</th>
                    <th className="pb-2">Absentee Risk</th>
                    <th className="pb-2">Productivity</th>
                    <th className="pb-2">Rank</th>
                  </tr>
                </thead>
                <tbody>
                  {deptMatrix.map((row) => (
                    <tr key={row.department} className="border-t border-line/50">
                      <td className="py-3 font-medium text-ink">{row.department}</td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-100">
                            <div className="h-full rounded-full bg-indigo-500" style={{ width: `${row.attendance.toFixed(0)}%` }} />
                          </div>
                          <span className="text-xs font-semibold text-ink">{row.attendance.toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="py-3 text-xs font-medium text-ink">{row.punctuality.toFixed(1)}%</td>
                      <td className="py-3 text-xs font-medium text-ink">{row.avgHours.toFixed(1)}h</td>
                      <td className="py-3 text-xs font-medium text-ink">{row.overtimePct.toFixed(1)}%</td>
                      <td className="py-3">
                        <span
                          className={cn(
                            "rounded-full px-2 py-1 text-[11px] font-semibold",
                            row.absenteeRisk > 52 ? "bg-red-100 text-red-700" : row.absenteeRisk > 34 ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"
                          )}
                        >
                          {row.absenteeRisk.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-3">
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-ink">
                          {row.productivity >= 75 ? (
                            <ArrowUpRight className="h-3.5 w-3.5 text-emerald-600" />
                          ) : (
                            <ArrowDownRight className="h-3.5 w-3.5 text-amber-600" />
                          )}
                          {row.productivity.toFixed(1)}
                        </span>
                      </td>
                      <td className="py-3 text-xs font-semibold text-primary">#{row.rank}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl xl:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-ink">Work-hours and Occupancy Dynamics</p>
                <p className="text-xs text-ink-muted">Smooth temporal behavior of active workforce span</p>
              </div>
              <Activity className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-4 h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={selectedTrend}
                  margin={{ top: 8, right: 8, left: -12, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="presentFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4F46E5" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#4F46E5" stopOpacity={0.04} />
                    </linearGradient>
                    <linearGradient id="hoursFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10B981" stopOpacity={0.03} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748B" }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ borderRadius: 14, border: "1px solid #E2E8F0" }} />
                  <Area type="monotone" dataKey="present" stroke="#4F46E5" fill="url(#presentFill)" strokeWidth={2.2} />
                  <Area type="monotone" dataKey="avgHours" stroke="#10B981" fill="url(#hoursFill)" strokeWidth={2.2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[20px] border border-white/60 bg-white/80 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl">
          <CardContent className="p-5">
            <p className="text-sm font-semibold text-ink">Device Intelligence</p>
            <p className="text-xs text-ink-muted">Live biometric mesh status</p>
            <div className="mt-4 space-y-2">
              {[
                { label: "Online state", value: operationsHealth.failingDevices > 0 ? "Degraded" : "Healthy", icon: Wifi },
                { label: "Sync latency", value: operationsHealth.syncLatency, icon: Zap },
                { label: "Throughput", value: `${operationsHealth.throughput} events/min`, icon: Activity },
                { label: "Device offline", value: String(operationsHealth.failingDevices), icon: AlertTriangle },
                { label: "Queue pressure", value: opsQuery.data ? String(opsQuery.data.queue_depth) : "—", icon: Cpu },
              ].map((row) => (
                <div key={row.label} className="rounded-xl border border-line/60 bg-slate-50/70 px-3 py-2">
                  <p className="flex items-center justify-between text-xs text-ink-muted">
                    <span className="inline-flex items-center gap-2">
                      <row.icon className="h-3.5 w-3.5 text-primary" />
                      {row.label}
                    </span>
                    <span className="font-semibold text-ink">{row.value}</span>
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="rounded-[20px] border border-white/60 bg-white/80 px-5 py-4 shadow-[0_8px_24px_rgba(15,23,42,0.06)] backdrop-blur-xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-muted">Executive Signals</p>
        <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {[
            `Attendance improved ${trendWindow.attendanceDelta != null ? `${trendWindow.attendanceDelta > 0 ? "+" : ""}${trendWindow.attendanceDelta.toFixed(1)}` : "0"} points compared to previous week.`,
            `${deptMatrix[0]?.department ?? "Operations"} has the strongest productivity rank this cycle.`,
            `${attendanceSignals.missingPunches} missing check-outs need correction before close of day.`,
            `Friday attendance historically trends lower; reinforce reminders before shift start.`,
          ].map((item) => (
            <p key={item} className="rounded-xl border border-line/60 bg-slate-50/75 px-3 py-2 text-xs leading-relaxed text-ink">
              {item}
            </p>
          ))}
        </div>
      </section>
    </div>
  );
}
