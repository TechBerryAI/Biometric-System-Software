import { motion } from "framer-motion";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "@/hooks/useAttendanceTrend";
import { formatDecimalHours, formatHoursMinutes } from "@/lib/dashboardAnalytics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const tooltipStyle = {
  background: "#FFFFFF",
  border: "1px solid #E2E8F0",
  borderRadius: 12,
  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
  fontSize: 12,
};

type Row = {
  label: string;
  avgHours: number | null;
  totalHours: number;
};

function toRows(data: TrendPoint[]): Row[] {
  return data.map((p) => ({
    label: p.label,
    avgHours: p.avgWorkMinutes != null ? p.avgWorkMinutes / 60 : null,
    totalHours: p.sumWorkMinutes / 60,
  }));
}

export function WorkHoursTrendChart({
  data,
  loading,
}: {
  data: TrendPoint[] | undefined;
  loading: boolean;
}) {
  if (loading || !data) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="mt-2 h-4 w-72" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[280px] w-full" />
        </CardContent>
      </Card>
    );
  }

  const chartData = toRows(data);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
      <Card className="overflow-hidden border-line/60 bg-surface-card/95">
        <CardHeader>
          <CardTitle>Hours on premises</CardTitle>
          <CardDescription>
            Average hours per present employee (line) and total person-hours (bars).
          </CardDescription>
        </CardHeader>
        <CardContent className="pb-2">
          <div className="h-[300px] w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="#E2E8F0" vertical={false} strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#64748B", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  dy={6}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: "#64748B", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={40}
                  label={{
                    value: "Avg h",
                    angle: -90,
                    position: "insideLeft",
                    fill: "#94A3B8",
                    fontSize: 10,
                  }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fill: "#64748B", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={44}
                  label={{
                    value: "Total h",
                    angle: 90,
                    position: "insideRight",
                    fill: "#94A3B8",
                    fontSize: 10,
                  }}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: "#0F172A", fontWeight: 600 }}
                  formatter={(value: number, name: string) => {
                    if (name === "Avg hours") {
                      if (value == null || Number.isNaN(value)) return ["No span data", name];
                      const mins = value * 60;
                      return [`${formatHoursMinutes(mins)} (${formatDecimalHours(mins)} h)`, name];
                    }
                    return [`${value.toFixed(1)} h`, name];
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, paddingTop: 12 }}
                  formatter={(value) => <span className="text-ink-muted">{value}</span>}
                />
                <Bar
                  yAxisId="right"
                  dataKey="totalHours"
                  name="Total person-hours"
                  fill="#C7D2FE"
                  radius={[6, 6, 0, 0]}
                  maxBarSize={36}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="avgHours"
                  name="Avg hours (present)"
                  stroke="#059669"
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: "#059669", strokeWidth: 0 }}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
