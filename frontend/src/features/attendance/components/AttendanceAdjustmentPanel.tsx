import { useCallback, useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { hasCapability } from "@/features/auth/sessionCapabilities";
import { useAuth } from "@/features/auth/AuthContext";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { fmtDisplayDate, fmtDisplayDateTime, isoToTimeParts, zonedWallClockToISO, type TimeParts } from "@/lib/dates";
import { applyAttendanceAdjustment, fetchAttendanceDayPreview, fetchCorrectionStatus, type AttendanceDayPreview } from "@/features/attendance/api";
import { getApiErrorMessage } from "@/shared/api/client";
import type { EmployeeDailyAttendance } from "@/types";

const EMPTY_TIME: TimeParts = { hour: 0, minute: 0, second: 0 };

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Number.isFinite(n) ? n : min));
}

type TimePartsEditorProps = {
  label: string;
  value: TimeParts | null;
  onChange: (value: TimeParts | null) => void;
  optional?: boolean;
};

function TimePartsEditor({ label, value, onChange, optional = false }: TimePartsEditorProps) {
  if (optional && value === null) {
    return (
      <div className="flex flex-col gap-1.5 text-sm">
        <span className="text-xs font-medium text-ink-muted">{label}</span>
        <Button type="button" variant="secondary" size="sm" className="w-fit" onClick={() => onChange({ ...EMPTY_TIME })}>
          Add check-out
        </Button>
      </div>
    );
  }

  const parts = value ?? EMPTY_TIME;

  const setPart = (key: keyof TimeParts, raw: string) => {
    const max = key === "hour" ? 23 : 59;
    const next = clamp(parseInt(raw, 10) || 0, 0, max);
    onChange({ ...parts, [key]: next });
  };

  return (
    <div className="flex flex-col gap-1.5 text-sm">
      <span className="text-xs font-medium text-ink-muted">{label}</span>
      <div className="flex items-center gap-1.5">
        <Input
          type="number"
          min={0}
          max={23}
          inputMode="numeric"
          aria-label={`${label} hour`}
          className="h-10 w-[4.25rem] px-2 text-center tabular-nums"
          value={parts.hour}
          onChange={(e) => setPart("hour", e.target.value)}
        />
        <span className="text-ink-muted">:</span>
        <Input
          type="number"
          min={0}
          max={59}
          inputMode="numeric"
          aria-label={`${label} minute`}
          className="h-10 w-[4.25rem] px-2 text-center tabular-nums"
          value={parts.minute}
          onChange={(e) => setPart("minute", e.target.value)}
        />
        <span className="text-ink-muted">:</span>
        <Input
          type="number"
          min={0}
          max={59}
          inputMode="numeric"
          aria-label={`${label} second`}
          className="h-10 w-[4.25rem] px-2 text-center tabular-nums"
          value={parts.second}
          onChange={(e) => setPart("second", e.target.value)}
        />
        {optional ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-1 h-8 px-2 text-xs text-ink-muted"
            onClick={() => onChange(null)}
          >
            Clear
          </Button>
        ) : null}
      </div>
      <p className="text-[11px] text-ink-subtle">Hour · minute · second (24h)</p>
    </div>
  );
}

type ModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employeeId: number;
  row: EmployeeDailyAttendance | null;
  onApplied: () => void;
};

export function AttendanceAdjustmentModal({
  open,
  onOpenChange,
  employeeId,
  row,
  onApplied,
}: ModalProps) {
  const { user } = useAuth();
  const canAdjust = hasCapability(user, "attendance_adjust");
  const date = row?.summary_date ?? "";
  const [checkInParts, setCheckInParts] = useState<TimeParts>(EMPTY_TIME);
  const [checkOutParts, setCheckOutParts] = useState<TimeParts | null>(null);
  const [preview, setPreview] = useState<AttendanceDayPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [applying, setApplying] = useState(false);
  const [pollingUuid, setPollingUuid] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadPreview = useCallback(async () => {
    if (!date) return;
    setLoadingPreview(true);
    setError(null);
    try {
      const data = await fetchAttendanceDayPreview(employeeId, date);
      setPreview(data);
      setCheckInParts(isoToTimeParts(data.current_check_in) ?? { hour: 9, minute: 0, second: 0 });
      setCheckOutParts(isoToTimeParts(data.current_check_out));
    } catch (e: unknown) {
      setError(getApiErrorMessage(e) || "Failed to load day preview");
    } finally {
      setLoadingPreview(false);
    }
  }, [employeeId, date]);

  useEffect(() => {
    if (!open || !date || !canAdjust) return;
    setSuccess(null);
    setError(null);
    void loadPreview();
    // Capabilities are optional; skip device probe on every modal open (slow on Tier B firmware).
  }, [open, date, canAdjust, loadPreview]);

  useEffect(() => {
    if (!pollingUuid) return;
    const terminal = new Set(["applied", "device_failed", "failed"]);
    const interval = window.setInterval(() => {
      void fetchCorrectionStatus(pollingUuid)
        .then((result) => {
          if (terminal.has(result.status)) {
            setPollingUuid(null);
            if (result.status === "applied") {
              setSuccess("Saved.");
            } else {
              setError(result.error_message || "Could not finish. Records were not changed.");
            }
            void loadPreview();
            onApplied();
          }
        })
        .catch(() => {
          /* keep polling */
        });
    }, 2000);
    return () => window.clearInterval(interval);
  }, [pollingUuid, loadPreview, onApplied]);

  if (!canAdjust) {
    return null;
  }

  const apply = async () => {
    if (!date) return;
    setApplying(true);
    setError(null);
    setSuccess(null);
    try {
      const newCheckIn = zonedWallClockToISO(date, checkInParts);
      const newCheckOut = checkOutParts ? zonedWallClockToISO(date, checkOutParts) : null;
      const result = await applyAttendanceAdjustment({
        employee_id: employeeId,
        local_date: date,
        new_check_in: newCheckIn,
        new_check_out: newCheckOut,
      });
      if (result.status === "device_pending") {
        if (!result.device_command_uuid) {
          setError("Save queued but no command id returned.");
          return;
        }
        setPollingUuid(result.device_command_uuid);
        setSuccess("Save in progress.");
        return;
      }
      setSuccess("Saved.");
      onApplied();
      await loadPreview();
    } catch (e: unknown) {
      setError(getApiErrorMessage(e) || "Update failed");
    } finally {
      setApplying(false);
    }
  };

  const previewCheckIn = date ? fmtDisplayDateTime(zonedWallClockToISO(date, checkInParts)) : "—";
  const previewCheckOut =
    date && checkOutParts ? fmtDisplayDateTime(zonedWallClockToISO(date, checkOutParts)) : "—";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Update times — {date ? fmtDisplayDate(date) : ""}</DialogTitle>
          <DialogDescription>
            Set check-in and check-out to the exact second. Times apply to this calendar day only.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {loadingPreview && !preview ? (
            <p className="text-sm text-ink-muted">Loading current punches…</p>
          ) : (
            <>
              {preview ? (
                <div className="rounded-xl border border-line/60 bg-surface/60 p-4 text-sm">
                  <p className="font-medium text-ink">Current on record</p>
                  <p className="mt-1 text-ink-muted">
                    In: {fmtDisplayDateTime(preview.current_check_in)} · Out: {fmtDisplayDateTime(preview.current_check_out)} ·
                    Punches: {preview.punch_count}
                  </p>
                  <p className="mt-3 font-medium text-ink">After update</p>
                  <p className="mt-1 text-ink-muted">
                    In: {previewCheckIn} · Out: {previewCheckOut}
                  </p>
                </div>
              ) : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <TimePartsEditor label="Check-in time" value={checkInParts} onChange={setCheckInParts} />
                <TimePartsEditor
                  label="Check-out time"
                  value={checkOutParts}
                  onChange={setCheckOutParts}
                  optional
                />
              </div>
            </>
          )}
          {error ? <p className="text-sm text-status-absent">{error}</p> : null}
          {success ? <p className="text-sm text-status-present">{success}</p> : null}
          {pollingUuid ? (
            <p className="text-xs text-ink-muted">Working…</p>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={applying}>
            Cancel
          </Button>
          <Button type="button" variant="secondary" onClick={() => void loadPreview()} disabled={loadingPreview || applying}>
            {loadingPreview ? "Refreshing…" : "Refresh preview"}
          </Button>
          <Button type="button" onClick={() => void apply()} disabled={applying || loadingPreview}>
            {applying ? "Applying…" : "Apply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type RowEditButtonProps = {
  onClick: () => void;
};

export function AttendanceRowEditButton({ onClick }: RowEditButtonProps) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-8 gap-1.5 px-2 text-primary hover:bg-primary-soft hover:text-primary"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      aria-label="Update times"
    >
      <Pencil className="h-3.5 w-3.5" />
      Update
    </Button>
  );
}
