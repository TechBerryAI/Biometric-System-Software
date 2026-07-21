import { useMutation } from "@tanstack/react-query";
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
import { createAppAccount } from "@/features/settings/api";
import { getApiErrorMessage } from "@/shared/api/client";
import { type AppUserRole } from "@/features/auth/api";

type Props = {
  open: boolean;
  onOpenChange: (value: boolean) => void;
};

const accountRoles: Array<{ value: AppUserRole; label: string }> = [
  { value: "CEO", label: "CEO" },
  { value: "HR_ADMIN", label: "HR Admin" },
  { value: "IT_ADMIN", label: "IT Admin" },
];

export function AddAccountModal({ open, onOpenChange }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AppUserRole>("IT_ADMIN");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setEmail("");
    setPassword("");
    setRole("IT_ADMIN");
    setFormError(null);
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      createAppAccount({
        email,
        password,
        role,
        active: true,
      }),
    onSuccess: () => {
      setFormError(null);
      onOpenChange(false);
    },
    onError: (error: unknown) => {
      setFormError(getApiErrorMessage(error));
    },
  });

  const submit = () => {
    setFormError(null);
    if (!email.trim()) {
      setFormError("Email is required.");
      return;
    }
    if (password.length < 8) {
      setFormError("Password must be at least 8 characters.");
      return;
    }
    mutation.mutate();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) setFormError(null);
        onOpenChange(value);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add account</DialogTitle>
          <DialogDescription>
            Create a management login for the web app. This is separate from biometric employee records.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="grid gap-2">
            <label className="text-xs font-medium text-ink-muted">Email</label>
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              autoComplete="email"
            />
          </div>
          <div className="grid gap-2">
            <label className="text-xs font-medium text-ink-muted">Password</label>
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Minimum 8 characters"
              autoComplete="new-password"
            />
          </div>
          <div className="grid gap-2">
            <label className="text-xs font-medium text-ink-muted">Role</label>
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as AppUserRole)}
              className="h-10 rounded-xl border border-line bg-surface-card px-3 text-sm text-ink shadow-sm transition-shadow hover:border-line focus-visible:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15"
            >
              {accountRoles.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </select>
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
                Creating
              </>
            ) : (
              "Create account"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
