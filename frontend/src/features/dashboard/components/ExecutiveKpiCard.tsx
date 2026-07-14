import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Sparkline } from "@/features/dashboard/components/Sparkline";
import { toneClasses } from "@/features/dashboard/utils/formatters";
import type { HealthTone } from "@/features/dashboard/utils/analytics";
import { cn } from "@/lib/cn";

export function ExecutiveKpiCard({
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
