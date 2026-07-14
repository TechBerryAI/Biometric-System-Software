import type { HealthTone, InsightSeverity } from "@/features/dashboard/utils/analytics";

export function toDeltaLabel(delta: number | null, suffix = "pts"): string {
  if (delta == null) return "No baseline";
  const abs = Math.abs(delta);
  if (abs < 0.1) return "Stable";
  return `${delta > 0 ? "+" : "-"}${abs.toFixed(1)} ${suffix}`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function parseShiftHour(shift: string | null): number | null {
  if (!shift) return null;
  const [h, m] = shift.split(":").map(Number);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  return h + m / 60;
}

export function readHour(iso: string | null): number | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.getHours() + date.getMinutes() / 60;
}

export function deltaPercentLabel(delta: number | null): string {
  if (delta == null) return "No historical baseline";
  const abs = Math.abs(delta);
  if (abs < 0.2) return "No major shift vs yesterday";
  return `${delta > 0 ? "+" : "-"}${abs.toFixed(1)}% vs yesterday`;
}

export function formatClock(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function toSpark(values: number[]): string {
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

export type ActionInsight = {
  id: string;
  title: string;
  severity: InsightSeverity;
  recommendation: string;
  actionLabel: string;
  actionHref: string;
};

export function toneClasses(tone: HealthTone): string {
  if (tone === "healthy") return "bg-emerald-100 text-emerald-700";
  if (tone === "risk") return "bg-red-100 text-red-700";
  return "bg-amber-100 text-amber-700";
}

export function severityClasses(severity: InsightSeverity): string {
  if (severity === "high") return "border-red-200 bg-red-50 text-red-700";
  if (severity === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}
