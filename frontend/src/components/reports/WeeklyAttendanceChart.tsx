import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "@/hooks/useAttendanceTrend";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const tooltipStyle = {
  background: "#FFFFFF",
  border: "1px solid #E2E8F0",
  borderRadius: 12,
  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
  fontSize: 12,
};

type DayRow = {
  label: string;
  present: number;
  absent: number;
  total: number;
  rate: number;
};

function buildWeekRows(data: TrendPoint[]): DayRow[] {
  return data.slice(-7).map((d) => {
    const total = d.headcount || d.present + d.absent;
    const rate = total > 0 ? Math.round((d.present / total) * 100) : 0;
    return {
      label: d.label,
      present: d.present,
      absent: d.absent,
      total,
      rate,
    };
  });
}

function niceYMax(maxValue: number): number {
  if (maxValue <= 5) return 5;
  if (maxValue <= 10) return 10;
  const step = maxValue <= 20 ? 5 : maxValue <= 50 ? 10 : 20;
  return Math.ceil(maxValue / step) * step;
}

function WeekTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number; dataKey?: string; payload?: DayRow }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;

  return (
    <div style={tooltipStyle} className="px-3 py-2.5">
      <p className="mb-1.5 text-xs font-semibold text-ink">{label}</p>
      <div className="space-y-1 text-xs text-ink-muted">
        <p>
          <span className="mr-1.5 inline-block h-2 w-2 rounded-sm bg-primary" />
          Present: <span className="font-medium text-ink">{row.present}</span>
        </p>
        <p>
          <span className="mr-1.5 inline-block h-2 w-2 rounded-sm bg-slate-300" />
          Absent: <span className="font-medium text-ink">{row.absent}</span>
        </p>
        <p className="border-t border-line/80 pt-1 font-medium text-ink">
          {row.rate}% attendance ({row.total} employees)
        </p>
      </div>
    </div>
  );
}

export function WeeklyAttendanceChart({
  data,
  loading,
}: {
  data: TrendPoint[] | undefined;
  loading: boolean;
}) {
  const week = useMemo(() => (data ? buildWeekRows(data) : []), [data]);

  const summary = useMemo(() => {
    const present = week.reduce((s, d) => s + d.present, 0);
    const absent = week.reduce((s, d) => s + d.absent, 0);
    const total = present + absent;
    const avgRate = total > 0 ? Math.round((present / total) * 100) : 0;
    return { present, absent, total, avgRate };
  }, [week]);

  const yMax = useMemo(() => {
    const peak = week.reduce((m, d) => Math.max(m, d.total), 0);
    return niceYMax(peak);
  }, [week]);

  if (loading || !data) {
    return (
      <Card className="h-full">
        <CardHeader>
          <Skeleton className="h-6 w-44" />
          <Skeleton className="mt-2 h-4 w-72" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-56 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle>Last 7 days</CardTitle>
        <CardDescription>
          How many employees checked in each day versus those marked absent.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-3 rounded-xl border border-line/80 bg-surface px-3 py-2.5">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">Avg attendance</p>
            <p className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{summary.avgRate}%</p>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">Present</p>
            <p className="mt-0.5 text-lg font-semibold tabular-nums text-primary">{summary.present}</p>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">Absent</p>
            <p className="mt-0.5 text-lg font-semibold tabular-nums text-ink-muted">{summary.absent}</p>
          </div>
        </div>

        <div className="h-52 w-full min-w-0">
          {week.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-ink-muted">
              No attendance data for this period.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={week} margin={{ top: 4, right: 8, left: 4, bottom: 0 }} barCategoryGap="20%">
                <CartesianGrid stroke="#E2E8F0" vertical={false} strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#64748B", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  dy={6}
                />
                <YAxis
                  domain={[0, yMax]}
                  tickCount={yMax <= 5 ? 6 : 5}
                  tick={{ fill: "#64748B", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                  width={36}
                  label={{
                    value: "Employees",
                    angle: -90,
                    position: "insideLeft",
                    fill: "#94A3B8",
                    fontSize: 10,
                    offset: 10,
                  }}
                />
                <Tooltip content={<WeekTooltip />} cursor={{ fill: "rgba(79, 70, 229, 0.04)" }} />
                <Legend
                  verticalAlign="bottom"
                  iconType="circle"
                  iconSize={8}
                  wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                  formatter={(value) => <span className="text-ink-muted">{value}</span>}
                />
                <Bar
                  dataKey="present"
                  name="Present"
                  stackId="day"
                  fill="#4F46E5"
                  radius={[0, 0, 0, 0]}
                  maxBarSize={40}
                />
                <Bar
                  dataKey="absent"
                  name="Absent"
                  stackId="day"
                  fill="#CBD5E1"
                  radius={[6, 6, 0, 0]}
                  maxBarSize={40}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
