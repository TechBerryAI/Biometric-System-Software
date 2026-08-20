import { useMutation } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
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
import { changeMyPassword } from "@/features/settings/api";
import { getApiErrorMessage } from "@/shared/api/client";

type Props = {
  open: boolean;
  onOpenChange: (value: boolean) => void;
};

export function ChangePasswordModal({ open, onOpenChange }: Props) {
  const { user, applyAuthTokens } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const resetForm = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setShowCurrent(false);
    setShowNew(false);
  };

  useEffect(() => {
    if (!open) return;
    resetForm();
    setMessage(null);
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      changeMyPassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      }),
    onSuccess: (tokens) => {
      applyAuthTokens(tokens);
      resetForm();
      setMessage({
        type: "success",
        text: "Password updated. Other signed-in devices have been signed out for your safety.",
      });
    },
    onError: (error: unknown) => {
      setMessage({ type: "error", text: getApiErrorMessage(error) });
    },
  });

  const submit = () => {
    setMessage(null);
    if (!currentPassword) {
      setMessage({ type: "error", text: "Enter your current password." });
      return;
    }
    if (newPassword.length < 8) {
      setMessage({ type: "error", text: "New password must be at least 8 characters." });
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage({ type: "error", text: "New password and confirmation do not match." });
      return;
    }
    if (newPassword === currentPassword) {
      setMessage({ type: "error", text: "New password must differ from your current password." });
      return;
    }
    mutation.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Change password</DialogTitle>
          <DialogDescription>Change the password for {user?.email ?? "your account"}.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="grid gap-2">
            <label htmlFor="current-password" className="text-xs font-medium text-ink-muted">
              Current password
            </label>
            <div className="relative">
              <Input
                id="current-password"
                type={showCurrent ? "text" : "password"}
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                autoComplete="current-password"
                placeholder="Enter current password"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 flex items-center px-3 text-ink-muted hover:text-ink"
                onClick={() => setShowCurrent((prev) => !prev)}
                aria-label={showCurrent ? "Hide current password" : "Show current password"}
              >
                {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="grid gap-2">
            <label htmlFor="new-password" className="text-xs font-medium text-ink-muted">
              New password
            </label>
            <div className="relative">
              <Input
                id="new-password"
                type={showNew ? "text" : "password"}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                autoComplete="new-password"
                placeholder="Minimum 8 characters"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 flex items-center px-3 text-ink-muted hover:text-ink"
                onClick={() => setShowNew((prev) => !prev)}
                aria-label={showNew ? "Hide new password" : "Show new password"}
              >
                {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="grid gap-2">
            <label htmlFor="confirm-password" className="text-xs font-medium text-ink-muted">
              Confirm new password
            </label>
            <Input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              autoComplete="new-password"
              placeholder="Re-enter new password"
            />
          </div>

          <p className="rounded-xl border border-line/60 bg-surface px-4 py-3 text-xs text-ink-muted leading-relaxed">
            For your safety, changing your password signs out all other active sessions. You will stay signed in on this
            device.
          </p>

          {message ? (
            <p
              className={
                message.type === "success"
                  ? "rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                  : "rounded-xl border border-status-absent-soft bg-status-absent-soft/40 px-3 py-2 text-sm text-status-absent"
              }
            >
              {message.text}
            </p>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
            {message?.type === "success" ? "Close" : "Cancel"}
          </Button>
          {message?.type === "success" ? null : (
            <Button type="button" onClick={submit} disabled={mutation.isPending}>
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Updating password
                </>
              ) : (
                "Update password"
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
