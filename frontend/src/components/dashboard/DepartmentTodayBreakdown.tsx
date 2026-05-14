import { motion } from "framer-motion";
import { Building2 } from "lucide-react";
import type { DepartmentTodayRow } from "@/lib/dashboardAnalytics";
import { formatDecimalHours, formatHoursMinutes } from "@/lib/dashboardAnalytics";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";

export function DepartmentTodayBreakdown({ rows }: { rows: DepartmentTodayRow[] }) {
  const visible = rows.filter((r) => r.registered > 0);

  if (visible.length === 0) {
    return null;
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.06 }}>
      <Card className="border-line/60 bg-surface-card/95">
        <CardHeader>
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-violet-soft text-violet">
              <Building2 className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <div>
              <CardTitle>Today by department</CardTitle>
              <CardDescription className="mt-1.5">
                Headcount from employee records; presence and hours from today&apos;s punch-derived summary.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-2 pt-0">
          <div className="scrollbar-thin overflow-x-auto px-6">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead>
                <tr className="text-xs font-medium uppercase tracking-wider text-ink-muted">
                  <th className="pb-3 pr-4">Department</th>
                  <th className="pb-3 pr-4 tabular-nums">Registered</th>
                  <th className="pb-3 pr-4 tabular-nums">Present</th>
                  <th className="pb-3 pr-4 tabular-nums">Attendance</th>
                  <th className="pb-3 tabular-nums">Avg span</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row, idx) => {
                  const rate = row.registered > 0 ? (row.present / row.registered) * 100 : 0;
                  return (
                    <tr
                      key={row.department}
                      className={cn(
                        "border-t border-line/50",
                        idx % 2 === 1 && "bg-surface/[0.35]"
                      )}
                    >
                      <td className="py-3 pr-4 font-medium text-ink">{row.department}</td>
                      <td className="py-3 pr-4 tabular-nums text-ink-muted">{row.registered}</td>
                      <td className="py-3 pr-4 tabular-nums text-ink">{row.present}</td>
                      <td className="py-3 pr-4 tabular-nums text-ink-muted">{rate.toFixed(0)}%</td>
                      <td className="py-3 tabular-nums text-ink-muted">
                        {row.avgWorkMinutes != null
                          ? `${formatHoursMinutes(row.avgWorkMinutes)} (${formatDecimalHours(row.avgWorkMinutes)} h)`
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
