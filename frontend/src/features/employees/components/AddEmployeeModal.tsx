import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
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
import { updateEmployee, upsertEmployee } from "@/features/employees/api";
import type { Employee } from "@/types";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  employee?: Employee | null;
};

const DEPARTMENT_OPTIONS = [
  "AI Department",
  "Accounts",
  "Digital Marketing",
  "HR Department",
  "IT / Administration",
  "MS SQL DBA",
  "MongoDB DBA",
  "MySQL DBA",
  "Operations",
  "Oracle DBA",
  "PostgreSQL DBA",
  "TechBerry Sales",
  "TiroNation Sales",
  "Training and Development",
] as const;

const OTHER_DEPARTMENT = "__other__";

function isKnownDepartment(value: string): value is (typeof DEPARTMENT_OPTIONS)[number] {
  return (DEPARTMENT_OPTIONS as readonly string[]).includes(value);
}

export function AddEmployeeModal({ open, onOpenChange, employee }: Props) {
  const qc = useQueryClient();
  const [deviceUserId, setDeviceUserId] = useState("");
  const [name, setName] = useState("");
  const [departmentSelection, setDepartmentSelection] = useState("");
  const [customDepartment, setCustomDepartment] = useState("");
  const [shiftStart, setShiftStart] = useState("");
  const [shiftEnd, setShiftEnd] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const isEditMode = Boolean(employee);
  const isOtherDepartment = departmentSelection === OTHER_DEPARTMENT;

  useEffect(() => {
    if (!open) return;
    if (employee) {
      const existingDepartment = employee.department ?? "";
      setDeviceUserId(employee.device_user_id);
      setName(employee.name);
      if (!existingDepartment) {
        setDepartmentSelection("");
        setCustomDepartment("");
      } else if (isKnownDepartment(existingDepartment)) {
        setDepartmentSelection(existingDepartment);
        setCustomDepartment("");
      } else {
        setDepartmentSelection(OTHER_DEPARTMENT);
        setCustomDepartment(existingDepartment);
      }
      setShiftStart(employee.shift_start ?? "");
      setShiftEnd(employee.shift_end ?? "");
      setFormError(null);
      return;
    }
    setDeviceUserId("");
    setName("");
    setDepartmentSelection("");
    setCustomDepartment("");
    setShiftStart("");
    setShiftEnd("");
    setFormError(null);
  }, [open, employee]);

  const mutation = useMutation({
    mutationFn: () => {
      const resolvedDepartment = isOtherDepartment
        ? customDepartment.trim()
        : departmentSelection.trim();
      const normalized = {
        device_user_id: deviceUserId.trim(),
        name: name.trim(),
        department: resolvedDepartment || null,
        shift_start: shiftStart.trim() || null,
        shift_end: shiftEnd.trim() || null,
      };
      if (isEditMode && employee) {
        return updateEmployee(employee.id, normalized);
      }
      return upsertEmployee(normalized);
    },
    onSuccess: () => {
      setFormError(null);
      void qc.invalidateQueries({ queryKey: ["employees"] });
      onOpenChange(false);
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
    if (isOtherDepartment && !customDepartment.trim()) {
      setFormError("Enter a department name when Other is selected.");
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
          <DialogTitle>{isEditMode ? "Edit employee" : "Add employee"}</DialogTitle>
          <DialogDescription>
            {isEditMode ? (
              <>
                Update employee metadata linked to{" "}
                <span className="font-mono text-xs">device_user_id</span>.
              </>
            ) : (
              <>
                Create a new employee metadata record by{" "}
                <span className="font-mono text-xs">device_user_id</span>.
              </>
            )}{" "}
            This does not push data to the terminal.
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
            <select
              value={departmentSelection}
              onChange={(e) => {
                const next = e.target.value;
                setDepartmentSelection(next);
                if (next !== OTHER_DEPARTMENT) setCustomDepartment("");
              }}
              className="h-10 rounded-xl border border-line bg-surface-card px-3 text-sm text-ink shadow-sm transition-shadow hover:border-line focus-visible:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15"
            >
              <option value="">Select department (optional)</option>
              {DEPARTMENT_OPTIONS.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}
                </option>
              ))}
              <option value={OTHER_DEPARTMENT}>Other</option>
            </select>
            {isOtherDepartment ? (
              <Input
                value={customDepartment}
                onChange={(e) => setCustomDepartment(e.target.value)}
                placeholder="Enter department name"
                autoComplete="off"
              />
            ) : null}
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
                {isEditMode ? "Saving changes" : "Creating"}
              </>
            ) : (
              (isEditMode ? "Save changes" : "Create employee")
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
