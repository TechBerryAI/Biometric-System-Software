import type { TrendPoint } from "@/features/attendance/hooks/useAttendanceTrend";
import type { DailySummaryRow, Employee } from "@/types";

export type TodayWorkStats = {
  attendanceRate: number | null;
  avgWorkMinutesAmongPresent: number | null;
  totalWorkMinutes: number;
  presentWithWorkData: number;
};

export function computeTodayWorkStats(
  summary: DailySummaryRow[],
  totalEmployees: number,
  presentToday: number
): TodayWorkStats {
  const withWork = summary.filter(
    (r) => r.first_check_in != null && r.total_work_minutes != null
  );
  const totalWorkMinutes = withWork.reduce((s, r) => s + (r.total_work_minutes ?? 0), 0);
  const avgWorkMinutesAmongPresent =
    withWork.length > 0 ? totalWorkMinutes / withWork.length : null;

  return {
    attendanceRate: totalEmployees > 0 ? (presentToday / totalEmployees) * 100 : null,
    avgWorkMinutesAmongPresent,
    totalWorkMinutes,
    presentWithWorkData: withWork.length,
  };
}

export type DepartmentTodayRow = {
  department: string;
  registered: number;
  present: number;
  avgWorkMinutes: number | null;
};

export function departmentTodayRollup(
  summary: DailySummaryRow[],
  employees: Employee[]
): DepartmentTodayRow[] {
  const byId = new Map(employees.map((e) => [e.id, e]));
  const deptOf = (employeeId: number) =>
    byId.get(employeeId)?.department?.trim() || "Unassigned";

  const reg = new Map<string, number>();
  for (const e of employees) {
    const d = e.department?.trim() || "Unassigned";
    reg.set(d, (reg.get(d) ?? 0) + 1);
  }

  const stats = new Map<string, { present: number; workSum: number; workN: number }>();
  for (const r of summary) {
    const d = deptOf(r.employee_id);
    if (!stats.has(d)) {
      stats.set(d, { present: 0, workSum: 0, workN: 0 });
    }
    const s = stats.get(d)!;
    if (r.first_check_in != null) {
      s.present += 1;
      if (r.total_work_minutes != null) {
        s.workSum += r.total_work_minutes;
        s.workN += 1;
      }
    }
  }

  const depts = new Set([...reg.keys(), ...stats.keys()]);
  return [...depts]
    .sort((a, b) => a.localeCompare(b))
    .map((department) => {
      const s = stats.get(department) ?? { present: 0, workSum: 0, workN: 0 };
      return {
        department,
        registered: reg.get(department) ?? 0,
        present: s.present,
        avgWorkMinutes: s.workN > 0 ? s.workSum / s.workN : null,
      };
    });
}

export function formatDecimalHours(minutes: number | null | undefined): string {
  if (minutes == null || Number.isNaN(minutes)) return "—";
  return (minutes / 60).toFixed(1);
}

export function formatHoursMinutes(minutes: number | null | undefined): string {
  if (minutes == null || Number.isNaN(minutes)) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h <= 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function mean(nums: number[]): number | null {
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

/** Plain-language bullets for leadership; uses trailing trend window. */
export function buildManagementInsights(
  trend: TrendPoint[],
  today: TodayWorkStats,
  presentToday: number,
  totalEmployees: number
): string[] {
  const out: string[] = [];

  if (totalEmployees > 0 && today.attendanceRate != null) {
    out.push(
      `Today ${today.attendanceRate.toFixed(0)}% of the roster clocked in (${presentToday} of ${totalEmployees}).`
    );
  }

  if (today.avgWorkMinutesAmongPresent != null && today.presentWithWorkData > 0) {
    const h = formatDecimalHours(today.avgWorkMinutesAmongPresent);
    out.push(
      `Among present staff with in/out coverage, average time on premises is about ${h} hours (${today.presentWithWorkData} people).`
    );
  } else if (presentToday > 0) {
    out.push(
      "Session duration is still sparse — many present staff are missing a paired checkout, so average hours are not shown."
    );
  }

  if (today.totalWorkMinutes > 0) {
    const th = formatDecimalHours(today.totalWorkMinutes);
    out.push(`Combined logged span across present staff today is roughly ${th} person-hours (sum of in→out minutes).`);
  }

  if (trend.length >= 7) {
    const last7 = trend.slice(-7);
    const prev7 = trend.slice(-14, -7);
    const mAttLast = mean(last7.map((p) => p.attendanceRatePercent));
    const mAttPrev = prev7.length >= 7 ? mean(prev7.map((p) => p.attendanceRatePercent)) : null;
    if (mAttLast != null && mAttPrev != null) {
      const delta = mAttLast - mAttPrev;
      const dir = delta >= 0.5 ? "up" : delta <= -0.5 ? "down" : "steady";
      if (dir === "up") {
        out.push(
          `Attendance rate over the last 7 days is trending up versus the prior week (about +${delta.toFixed(1)} points on average).`
        );
      } else if (dir === "down") {
        out.push(
          `Attendance rate over the last 7 days is softer than the week before (about ${delta.toFixed(1)} points lower on average).`
        );
      }
    }

  }

  return out.slice(0, 5);
}

export type DeltaTone = "positive" | "negative" | "neutral";
export type HealthTone = "healthy" | "watch" | "risk";
export type InsightSeverity = "low" | "medium" | "high";

export function toDeltaTone(delta: number | null): DeltaTone {
  if (delta == null) return "neutral";
  if (Math.abs(delta) < 0.1) return "neutral";
  return delta > 0 ? "positive" : "negative";
}

/** For metrics where a decrease is good (late arrivals, missing punches, overtime). */
export function toInvertedDeltaTone(delta: number | null): DeltaTone {
  const tone = toDeltaTone(delta);
  if (tone === "positive") return "negative";
  if (tone === "negative") return "positive";
  return "neutral";
}

export function healthToneFromThresholds(
  value: number,
  healthyAt: number,
  watchAt: number,
  higherIsBetter = true
): HealthTone {
  if (higherIsBetter) {
    if (value >= healthyAt) return "healthy";
    if (value >= watchAt) return "watch";
    return "risk";
  }
  if (value <= healthyAt) return "healthy";
  if (value <= watchAt) return "watch";
  return "risk";
}

export function dateRangeToDays(label: string): number {
  if (label === "Today") return 1;
  if (label === "Last 7 days") return 7;
  if (label === "Last 30 days") return 30;
  return 14;
}
