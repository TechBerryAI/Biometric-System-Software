import { motion } from "framer-motion";
import { Lightbulb } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function ManagementInsightsCard({
  bullets,
  source,
  loading = false,
  cached = false,
  errorCode,
}: {
  bullets: string[];
  /** When grok, copy is generated server-side from live aggregates; charts stay code-driven. */
  source?: "grok" | "rules" | "cache" | "error" | "unconfigured";
  loading?: boolean;
  cached?: boolean;
  errorCode?: string | null;
}) {
  const sourceLabel =
    source === "grok"
      ? "AI source: Grok"
      : source === "cache"
      ? "AI source: Cached Grok result"
      : source === "error"
      ? "AI source: unavailable"
      : source === "unconfigured"
      ? "AI source: not configured"
      : "AI source: local deterministic rules";

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.08 }}>
      <Card className="border-line/60 bg-surface-card/95">
        <CardHeader>
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-primary/15 bg-primary-soft text-primary">
              <Lightbulb className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <div>
              <CardTitle>What this means for management</CardTitle>
              <CardDescription className="mt-1.5 space-y-1">
                <span className="block">
                  {source === "grok" || source === "cache"
                  ? "Narrative from Grok using aggregate attendance from this app (no chart generation). Visuals above are rendered in code from the same underlying data."
                  : "Short takeaways from today's numbers and the recent trend — suitable for standups or email updates."}
                </span>
                <span className="block text-xs">
                  {sourceLabel}
                  {cached ? " • cache hit" : ""}
                  {errorCode ? ` • ${errorCode.replace(/_/g, " ")}` : ""}
                </span>
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-ink-muted">Generating AI summary from aggregate attendance...</p>
          ) : bullets.length === 0 ? (
            <p className="text-sm text-ink-muted">Load attendance data to see automated summaries.</p>
          ) : (
            <ul className="space-y-3 text-sm leading-relaxed text-ink">
              {bullets.map((b, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
