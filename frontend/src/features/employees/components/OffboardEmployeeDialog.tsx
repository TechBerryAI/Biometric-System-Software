import { useState } from "react";
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

type OffboardEmployeeDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employeeName: string;
  deviceUserId: string;
  onConfirm: () => Promise<void>;
};

export function OffboardEmployeeDialog({
  open,
  onOpenChange,
  employeeName,
  deviceUserId,
  onConfirm,
}: OffboardEmployeeDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to offboard employee");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) {
          setError(null);
          onOpenChange(next);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Offboard employee</DialogTitle>
          <DialogDescription>
            Remove <span className="font-medium text-ink">{employeeName}</span> (
            <span className="font-mono text-xs">{deviceUserId}</span>) from the employee directory and
            biometric device. Historical attendance records are kept in the database.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <p className="text-sm text-ink-muted">
            This removes their fingerprint from the terminal. Re-enrollment is required if they return.
          </p>
          {error ? <p className="mt-3 text-sm text-status-absent">{error}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" onClick={() => void handleConfirm()} disabled={busy}>
            {busy ? "Offboarding…" : "Offboard"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
