import { useCallback, useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { isGodMode } from "@/auth/godMode";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  applyGodAttendanceCorrection,
  fetchGodDayPreview,
  getApiErrorMessage,
  type GodDayPreview,
} from "@/services/api";
import type { EmployeeDailyAttendance } from "@/types";

function toLocalInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtDateTime(v: string | null): string {
  if (!v) return "—";
  return new Date(v).toLocaleString();
}

function fmtDate(v: string): string {
  return new Date(`${v}T12:00:00`).toLocaleDateString();
}

type ModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employeeId: number;
  row: EmployeeDailyAttendance | null;
  onApplied: () => void;
};

export function GodAttendanceCorrectionModal({
  open,
  onOpenChange,
  employeeId,
  row,
  onApplied,
}: ModalProps) {
  const { user } = useAuth();
  const godMode = isGodMode(user);
  const date = row?.summary_date ?? "";
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [preview, setPreview] = useState<GodDayPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadPreview = useCallback(async () => {
    if (!date) return;
    setLoadingPreview(true);
    setError(null);
    try {
      const data = await fetchGodDayPreview(employeeId, date);
      setPreview(data);
      setCheckIn(toLocalInputValue(data.current_check_in));
      setCheckOut(toLocalInputValue(data.current_check_out));
    } catch (e: unknown) {
      setError(getApiErrorMessage(e) || "Failed to load day preview");
    } finally {
      setLoadingPreview(false);
    }
  }, [employeeId, date]);

  useEffect(() => {
    if (!open || !date || !godMode) return;
    setSuccess(null);
    setError(null);
    void loadPreview();
  }, [open, date, godMode, loadPreview]);

  if (!godMode) {
    return null;
  }

  const apply = async () => {
    if (!date) return;
    if (!checkIn) {
      setError("Check-in time is required.");
      return;
    }
    setApplying(true);
    setError(null);
    setSuccess(null);
    try {
      const newCheckIn = new Date(checkIn);
      const newCheckOut = checkOut ? new Date(checkOut) : null;
      const result = await applyGodAttendanceCorrection({
        employee_id: employeeId,
        local_date: date,
        new_check_in: newCheckIn.toISOString(),
        new_check_out: newCheckOut?.toISOString() ?? null,
      });
      setSuccess(
        result.status === "applied_db_only"
          ? "Attendance updated in the database. This device firmware cannot rewrite punch memory; sync suppressions prevent old device punches from returning."
          : "Attendance updated on device and across all records.",
      );
      onApplied();
      await loadPreview();
    } catch (e: unknown) {
      setError(getApiErrorMessage(e) || "Correction failed");
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-status-absent">Edit attendance — {date ? fmtDate(date) : ""}</DialogTitle>
          <DialogDescription>
            Updates check-in and check-out in the database (and on the device when firmware supports it). Corrected
            times appear as original punches in reports; old device punches are suppressed from re-sync.
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
                    In: {fmtDateTime(preview.current_check_in)} · Out: {fmtDateTime(preview.current_check_out)} ·
                    Punches: {preview.punch_count}
                  </p>
                  <p className="mt-3 font-medium text-ink">After correction</p>
                  <p className="mt-1 text-ink-muted">
                    In: {checkIn ? new Date(checkIn).toLocaleString() : "—"} · Out:{" "}
                    {checkOut ? new Date(checkOut).toLocaleString() : "—"}
                  </p>
                </div>
              ) : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="text-xs font-medium text-ink-muted">Check-in</span>
                  <Input type="datetime-local" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="text-xs font-medium text-ink-muted">Check-out</span>
                  <Input
                    type="datetime-local"
                    value={checkOut}
                    onChange={(e) => setCheckOut(e.target.value)}
                    placeholder="Optional"
                  />
                </label>
              </div>
            </>
          )}
          {error ? <p className="text-sm text-status-absent">{error}</p> : null}
          {success ? <p className="text-sm text-status-present">{success}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={applying}>
            Cancel
          </Button>
          <Button type="button" variant="secondary" onClick={() => void loadPreview()} disabled={loadingPreview || applying}>
            {loadingPreview ? "Refreshing…" : "Refresh preview"}
          </Button>
          <Button type="button" onClick={() => void apply()} disabled={applying || loadingPreview || !checkIn}>
            {applying ? "Applying…" : "Apply correction"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type RowEditButtonProps = {
  onClick: () => void;
};

export function GodAttendanceRowEditButton({ onClick }: RowEditButtonProps) {
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
      aria-label="Edit attendance"
    >
      <Pencil className="h-3.5 w-3.5" />
      Edit
    </Button>
  );
}
