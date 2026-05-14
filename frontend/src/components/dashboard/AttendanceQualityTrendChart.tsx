import { motion } from "framer-motion";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
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

export function AttendanceQualityTrendChart({
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
          <Skeleton className="h-6 w-56" />
          <Skeleton className="mt-2 h-4 w-64" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[280px] w-full" />
        </CardContent>
      </Card>
    );
  }

  const chartData = data.map((p) => ({
    label: p.label,
    attendanceRate: Math.round(p.attendanceRatePercent * 10) / 10,
    absenteeismRate: p.headcount > 0 ? Math.round((p.absent / p.headcount) * 1000) / 10 : 0,
  }));

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.05 }}>
      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle>Attendance and absenteeism rates</CardTitle>
          <CardDescription>
            Share of the roster that punched in versus share of roster absent. Both are percentages for easy
            comparison.
          </CardDescription>
        </CardHeader>
        <CardContent className="pb-2">
          <div className="h-[300px] w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="#E2E8F0" vertical={false} strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#64748B", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  dy={6}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: "#64748B", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={36}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: "#0F172A", fontWeight: 600 }}
                  formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name]}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, paddingTop: 12 }}
                  formatter={(value) => <span className="text-ink-muted">{value}</span>}
                />
                <Line
                  type="monotone"
                  dataKey="attendanceRate"
                  name="Roster punched in"
                  stroke="#059669"
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: "#059669", strokeWidth: 0 }}
                />
                <Line
                  type="monotone"
                  dataKey="absenteeismRate"
                  name="Roster absent"
                  stroke="#94A3B8"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={{ r: 2.5, fill: "#94A3B8", strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
