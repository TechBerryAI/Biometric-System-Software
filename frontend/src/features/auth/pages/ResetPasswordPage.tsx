import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { confirmPasswordReset } from "@/features/auth/api";
import { getApiErrorMessage } from "@/shared/api/client";

export function ResetPassword() {
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState(searchParams.get("email")?.trim().toLowerCase() ?? "");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email.trim()) {
      setError("Enter the email for this account.");
      return;
    }
    if (!/^\d{6}$/.test(otp.trim())) {
      setError("Enter the 6-digit code from your email.");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await confirmPasswordReset({
        email,
        otp: otp.trim(),
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setSubmitted(true);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Reset password</CardTitle>
          <CardDescription>Enter the 6-digit email code, then choose a new password.</CardDescription>
        </CardHeader>
        <CardContent>
          {submitted ? (
            <div className="space-y-4">
              <p className="text-sm text-ink-muted">Your password has been updated. You can sign in with the new password.</p>
              <Button className="w-full" asChild>
                <Link to="/login">Sign in</Link>
              </Button>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={onSubmit}>
              <div className="space-y-2">
                <label className="text-xs font-medium text-ink-muted">Email</label>
                <Input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="admin@company.com"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium text-ink-muted">Verification code</label>
                <Input
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  maxLength={6}
                  placeholder="6-digit code"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium text-ink-muted">New password</label>
                <Input
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  placeholder="Minimum 8 characters"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium text-ink-muted">Confirm new password</label>
                <Input
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  placeholder="Re-enter new password"
                />
              </div>
              {error ? <p className="text-xs text-destructive">{error}</p> : null}
              <Button className="w-full" type="submit" disabled={submitting}>
                {submitting ? "Updating..." : "Update password"}
              </Button>
              <div className="text-center">
                <Link to="/forgot-password" className="text-xs font-medium text-ink-muted hover:text-ink">
                  Request a new code
                </Link>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
