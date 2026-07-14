import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import type { Permission } from "./permissions";
import type { ReactNode } from "react";

export function RequireAuth({ children, permission }: { children: ReactNode; permission?: Permission }) {
  const { user, loading, can } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-ink-muted">Loading session...</div>;
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  if (permission && !can(permission)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
