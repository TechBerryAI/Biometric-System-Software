import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { requestPasswordReset } from "@/features/auth/api";
import { getApiErrorMessage } from "@/shared/api/client";

const SUCCESS_MESSAGE = "We sent a reset link to that email. Check your inbox.";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await requestPasswordReset(email);
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
          <CardTitle>Forgot password</CardTitle>
          <CardDescription>
            Enter the email of an existing management account. A reset link is sent only if that account is already in
            the system.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {submitted ? (
            <div className="space-y-4">
              <p className="text-sm text-ink-muted">{SUCCESS_MESSAGE}</p>
              <Button className="w-full" asChild>
                <Link to="/login">Back to sign in</Link>
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
              {error ? <p className="text-xs text-destructive">{error}</p> : null}
              <Button className="w-full" type="submit" disabled={submitting}>
                {submitting ? "Sending..." : "Send reset link"}
              </Button>
              <div className="text-center">
                <Link to="/login" className="text-xs font-medium text-ink-muted hover:text-ink">
                  Back to sign in
                </Link>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
