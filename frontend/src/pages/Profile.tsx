import { useMutation } from "@tanstack/react-query";
import { Loader2, PencilLine } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage, updateMyProfile } from "@/services/api";

const GOD_MODE_EMAIL = "techberryaiteam@gmail.com";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function Profile() {
  const { user, refreshUser } = useAuth();
  const [fullName, setFullName] = useState("");
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const isGodMode = (user?.email ?? "").trim().toLowerCase() === GOD_MODE_EMAIL;
  const accountName = user?.full_name?.trim() || "Not set";
  const roleLabel = isGodMode ? "GOD mode" : user?.role === "HR_ADMIN" ? "HR/Admin" : user?.role ?? "Unknown";
  const accountTier = isGodMode ? "god" : user?.role === "CEO" ? "ceo" : user?.role === "HR_ADMIN" ? "hr" : "other";

  useEffect(() => {
    setFullName(user?.full_name ?? "");
    setMessage(null);
    setEditing(false);
  }, [user?.full_name]);

  const saveMutation = useMutation({
    mutationFn: () => updateMyProfile({ full_name: fullName }),
    onSuccess: async () => {
      await refreshUser();
      setEditing(false);
      setMessage("Profile updated successfully.");
    },
    onError: (error: unknown) => {
      setMessage(getApiErrorMessage(error));
    },
  });

  const saveProfile = () => {
    setMessage(null);
    if (!fullName.trim()) {
      setMessage("Name is required.");
      return;
    }
    saveMutation.mutate();
  };

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-display-xl text-ink">My Profile</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Account details used for login and access control in this attendance platform.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="relative overflow-hidden lg:col-span-2">
          <div
            className={
              accountTier === "god"
                ? "h-1.5 w-full bg-gradient-to-r from-status-absent via-status-absent to-status-absent-soft"
                : accountTier === "ceo"
                ? "h-1.5 w-full bg-gradient-to-r from-status-late via-status-late to-status-late-soft"
                : "h-1.5 w-full bg-gradient-to-r from-primary via-primary to-primary-soft"
            }
          />
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>Profile details</CardTitle>
              <Button
                type="button"
                variant={editing ? "secondary" : "ghost"}
                size="sm"
                onClick={() => {
                  setMessage(null);
                  setFullName(user?.full_name ?? "");
                  setEditing((prev) => !prev);
                }}
              >
                <PencilLine className="h-4 w-4" />
                {editing ? "Editing" : "Edit"}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="mb-2 flex items-center gap-3 rounded-2xl border border-line/70 bg-surface p-3">
              <span
                className={
                  accountTier === "god"
                    ? "flex h-11 w-11 items-center justify-center rounded-xl bg-status-absent-soft text-sm font-semibold text-status-absent"
                    : accountTier === "ceo"
                    ? "flex h-11 w-11 items-center justify-center rounded-xl bg-status-late-soft text-sm font-semibold text-status-late"
                    : "flex h-11 w-11 items-center justify-center rounded-xl bg-primary-soft text-sm font-semibold text-primary"
                }
              >
                {initials(accountName === "Not set" ? user?.email ?? "U" : accountName)}
              </span>
              <div>
                <p className="text-sm font-semibold text-ink">{accountName}</p>
                <p className="text-xs text-ink-muted">{user?.email ?? "—"}</p>
              </div>
            </div>

            {editing ? (
              <div className="space-y-4">
                <div className="grid gap-2">
                  <label className="text-xs font-medium text-ink-muted">Full name</label>
                  <Input
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="Enter your full name"
                    maxLength={160}
                  />
                </div>
                <div className="grid gap-2">
                  <label className="text-xs font-medium text-ink-muted">Email</label>
                  <Input value={user?.email ?? ""} readOnly />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" onClick={saveProfile} disabled={saveMutation.isPending}>
                    {saveMutation.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Saving
                      </>
                    ) : (
                      "Update profile"
                    )}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      setFullName(user?.full_name ?? "");
                      setEditing(false);
                      setMessage(null);
                    }}
                    disabled={saveMutation.isPending}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="grid gap-5 sm:grid-cols-2">
                <Detail label="Account name" value={accountName} />
                <Detail label="Email" value={user?.email ?? "—"} />
                <Detail label="Role" value={roleLabel} />
                <Detail label="Account status" value={user?.active ? "Active" : "Inactive"} />
                <Detail label="User UUID" value={user?.user_uuid ?? "—"} mono />
              </div>
            )}
            {message ? <p className="text-sm text-ink-muted">{message}</p> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Access tier</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Badge
              variant={isGodMode ? "absent" : user?.role === "CEO" ? "outline" : "default"}
              className={user?.role === "CEO" ? "border-status-late-soft bg-status-late-soft text-status-late" : ""}
            >
              {roleLabel}
            </Badge>
            <p className="text-sm text-ink-muted leading-relaxed">
              Your visible pages and actions are controlled by this account role.
            </p>
            <div className="rounded-xl border border-line/70 bg-surface px-3 py-2">
              <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Access status</p>
              <p className="mt-1 text-sm font-medium text-ink">{user?.active ? "Active account" : "Inactive account"}</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">{label}</p>
      <p className={`mt-1 text-sm text-ink ${mono ? "font-mono text-xs break-all" : ""}`}>{value}</p>
    </div>
  );
}
