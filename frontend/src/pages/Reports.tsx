import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Download, FileSpreadsheet } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AttendanceTrendChart } from "@/components/dashboard/AttendanceTrendChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAttendanceTrend } from "@/hooks/useAttendanceTrend";
import type { ExportPeriod } from "@/lib/dates";
import { dateList, getExportRange, todayISO } from "@/lib/dates";
import { fetchDailySummary } from "@/services/api";
import type { DailySummaryRow } from "@/types";
import { downloadAttendanceSummaryPdf } from "@/utils/pdfReports";

const tooltipStyle = {
  background: "#FFFFFF",
  border: "1px solid #E2E8F0",
  borderRadius: 12,
  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
  fontSize: 12,
};

export function Reports() {
  const [anchorDate, setAnchorDate] = useState(todayISO);
  const [period, setPeriod] = useState<ExportPeriod>("week");
  const trend = useAttendanceTrend(14);

  const range = useMemo(() => getExportRange(anchorDate, period), [anchorDate, period]);

  const exportMutation = useMutation({
    mutationFn: async () => {
      const dates = dateList(range.from, range.to);
      const allRows: Array<DailySummaryRow & { summary_date: string }> = [];
      for (const day of dates) {
        const summary = await fetchDailySummary(day);
        for (const row of summary) {
          allRows.push({ ...row, summary_date: day });
        }
      }
      downloadAttendanceSummaryPdf({ periodLabel: range.label, rows: allRows });
    },
  });

  const barData = useMemo(() => {
    if (!trend.data) return [];
    const slice = trend.data.slice(-7);
    return slice.map((d) => ({
      name: d.label,
      present: d.present,
      absent: d.absent,
    }));
  }, [trend.data]);

  return (
    <div className="space-y-10">
      <header>
        <h1 className="font-display text-display-xl text-ink">Reports</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Export attendance packets and scan short-range summaries without leaving the console.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-primary">
              <FileSpreadsheet className="h-5 w-5" strokeWidth={1.75} />
              <CardTitle>PDF export</CardTitle>
            </div>
            <CardDescription>Roll up every employee across your chosen window into one document.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-xs font-medium text-ink-muted">End date</span>
              <Input type="date" value={anchorDate} onChange={(e) => setAnchorDate(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-xs font-medium text-ink-muted">Window</span>
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value as ExportPeriod)}
                className="h-10 rounded-xl border border-line bg-surface-card px-3 text-sm shadow-sm focus-visible:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15"
              >
                <option value="day">Single day</option>
                <option value="week">Last 7 days</option>
                <option value="month">Last 30 days</option>
              </select>
            </label>
            <p className="rounded-xl border border-line/80 bg-surface px-3 py-2 text-xs text-ink-muted leading-relaxed">
              {range.label}
            </p>
            <Button
              type="button"
              className="w-full sm:w-auto"
              onClick={() => exportMutation.mutate()}
              disabled={exportMutation.isPending}
            >
              <Download className="h-4 w-4" />
              {exportMutation.isPending ? "Building PDF…" : "Download PDF"}
            </Button>
            {exportMutation.isError ? (
              <p className="text-sm text-status-absent">
                {exportMutation.error instanceof Error ? exportMutation.error.message : "Export failed"}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Seven-day composition</CardTitle>
              <CardDescription>Present vs absent counts — trailing week slice of the trend.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-56 w-full min-w-0">
                {trend.isLoading ? (
                  <div className="flex h-full items-center justify-center text-sm text-ink-muted">Loading chart…</div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={barData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                      <CartesianGrid stroke="#E2E8F0" vertical={false} strokeDasharray="3 3" />
                      <XAxis dataKey="name" tick={{ fill: "#64748B", fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis
                        tick={{ fill: "#64748B", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        allowDecimals={false}
                        width={32}
                      />
                      <Tooltip
                        contentStyle={tooltipStyle}
                        labelStyle={{ color: "#0F172A", fontWeight: 600 }}
                      />
                      <Bar dataKey="present" name="Present" fill="#4F46E5" radius={[6, 6, 0, 0]} />
                      <Bar dataKey="absent" name="Absent" fill="#CBD5E1" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      <AttendanceTrendChart data={trend.data} loading={trend.isLoading} />
    </div>
  );
}
