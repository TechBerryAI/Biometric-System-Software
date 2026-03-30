import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { upsertEmployee } from "@/services/api";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

export function AddEmployeeModal({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const [deviceUserId, setDeviceUserId] = useState("");
  const [name, setName] = useState("");
  const [department, setDepartment] = useState("");
  const [shiftStart, setShiftStart] = useState("");
  const [shiftEnd, setShiftEnd] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      upsertEmployee({
        device_user_id: deviceUserId.trim(),
        name: name.trim(),
        department: department.trim() || null,
        shift_start: shiftStart.trim() || null,
        shift_end: shiftEnd.trim() || null,
      }),
    onSuccess: () => {
      setFormError(null);
      void qc.invalidateQueries({ queryKey: ["employees"] });
      onOpenChange(false);
      setDeviceUserId("");
      setName("");
      setDepartment("");
      setShiftStart("");
      setShiftEnd("");
    },
    onError: (e: unknown) => {
      setFormError(e instanceof Error ? e.message : "Could not save employee");
    },
  });

  const submit = () => {
    setFormError(null);
    if (!deviceUserId.trim() || !name.trim()) {
      setFormError("Device user ID and name are required.");
      return;
    }
    mutation.mutate();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) setFormError(null);
        onOpenChange(v);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add or update employee</DialogTitle>
          <DialogDescription>
            Upserts metadata by <span className="font-mono text-xs">device_user_id</span>. Does not push to the
            terminal.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="grid gap-2">
            <label className="text-xs font-medium text-ink-muted">Device user ID</label>
            <Input
              value={deviceUserId}
              onChange={(e) => setDeviceUserId(e.target.value)}
              placeholder="Terminal user id"
              autoComplete="off"
            />
          </div>
          <div className="grid gap-2">
            <label className="text-xs font-medium text-ink-muted">Display name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" />
          </div>
          <div className="grid gap-2">
            <label className="text-xs font-medium text-ink-muted">Department</label>
            <Input
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">Shift start</label>
              <Input type="time" value={shiftStart} onChange={(e) => setShiftStart(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">Shift end</label>
              <Input type="time" value={shiftEnd} onChange={(e) => setShiftEnd(e.target.value)} />
            </div>
          </div>
          {formError ? (
            <p className="rounded-xl border border-status-absent-soft bg-status-absent-soft/40 px-3 py-2 text-sm text-status-absent">
              {formError}
            </p>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving
              </>
            ) : (
              "Save"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
