import { useEffect, useState } from "react";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { fetchDayPunches } from "@/features/attendance/api";
import { fmtDisplayDate, fmtDisplayDateTime } from "@/lib/dates";
import { cn } from "@/lib/cn";
import { getApiErrorMessage } from "@/shared/api/client";
import type { DayPunch, DayPunchesResponse } from "@/types";

function roleLabel(role: string): string {
  if (role === "in") return "In";
  if (role === "out") return "Out";
  return "Punch";
}

function roleClass(role: string): string {
  if (role === "in") return "bg-status-present-soft text-status-present";
  if (role === "out") return "bg-status-absent-soft text-status-absent";
  return "bg-surface text-ink-muted";
}

function fmtWorkHm(total: number | null): string {
  if (total == null) return "—";
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

type DayPunchesDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employeeId: number | null;
  employeeName: string;
  date: string;
};

export function DayPunchesDialog({
  open,
  onOpenChange,
  employeeId,
  employeeName,
  date,
}: DayPunchesDialogProps) {
  const [data, setData] = useState<DayPunchesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || employeeId == null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    void fetchDayPunches(employeeId, date)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(getApiErrorMessage(e) || "Failed to load punches");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, employeeId, date]);

  const punches: DayPunch[] = data?.punches ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{employeeName}</DialogTitle>
          <DialogDescription>
            All machine punches for {fmtDisplayDate(date)}
            {data?.device_user_id ? ` · ${data.device_user_id}` : null}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">In</p>
              <p className="mt-1 text-ink">{fmtDisplayDateTime(data?.first_check_in ?? null)}</p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Out</p>
              <p className="mt-1 text-ink">{fmtDisplayDateTime(data?.last_check_out ?? null)}</p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Total</p>
              <p className="mt-1 tabular-nums text-ink">{fmtWorkHm(data?.total_work_minutes ?? null)}</p>
            </div>
          </div>

          {loading ? <p className="text-sm text-ink-muted">Loading punches…</p> : null}
          {error ? <p className="text-sm text-status-absent">{error}</p> : null}

          {!loading && !error ? (
            punches.length === 0 ? (
              <p className="text-sm text-ink-muted">No punches stored for this day.</p>
            ) : (
              <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
                {punches.map((punch) => (
                  <li
                    key={punch.id}
                    className="flex items-start justify-between gap-3 rounded-xl border border-line/60 bg-surface/40 px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-ink">{fmtDisplayDateTime(punch.timestamp)}</p>
                      <p className="mt-0.5 truncate text-xs text-ink-muted font-mono">{punch.device_id}</p>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 rounded-md px-2 py-0.5 text-xs font-medium",
                        roleClass(punch.role)
                      )}
                    >
                      {roleLabel(punch.role)}
                    </span>
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
