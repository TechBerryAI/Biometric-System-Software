import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { hasCapability } from "@/features/auth/sessionCapabilities";
import { AppLayout } from "@/components/layout/AppLayout";
import { PageFallback } from "@/components/layout/PageFallback";
import { ForgotPassword } from "@/features/auth/pages/ForgotPasswordPage";
import { Login } from "@/features/auth/pages/LoginPage";
import { ResetPassword } from "@/features/auth/pages/ResetPasswordPage";

// Each page (and its charts / export libraries) is its own chunk so the first screen loads fast.
const pageModules = {
  attendance: () => import("@/features/attendance/pages/AttendancePage"),
  audit: () => import("@/features/audit/pages/AuditPage"),
  dashboard: () => import("@/features/dashboard/pages/DashboardPage"),
  employeeProfile: () => import("@/features/employees/pages/EmployeeProfilePage"),
  employees: () => import("@/features/employees/pages/EmployeesPage"),
  monitoring: () => import("@/features/monitoring/pages/RealtimeMonitoringPage"),
  operations: () => import("@/features/operations/pages/OperationsPage"),
  profile: () => import("@/features/settings/pages/ProfilePage"),
  reports: () => import("@/features/reports/pages/ReportsPage"),
  settings: () => import("@/features/settings/pages/SettingsPage"),
};

const Attendance = lazy(() => pageModules.attendance().then((m) => ({ default: m.Attendance })));
const Audit = lazy(() => pageModules.audit().then((m) => ({ default: m.Audit })));
const Dashboard = lazy(() => pageModules.dashboard().then((m) => ({ default: m.Dashboard })));
const EmployeeProfile = lazy(() => pageModules.employeeProfile().then((m) => ({ default: m.EmployeeProfile })));
const Employees = lazy(() => pageModules.employees().then((m) => ({ default: m.Employees })));
const RealtimeMonitoring = lazy(() => pageModules.monitoring().then((m) => ({ default: m.RealtimeMonitoring })));
const Operations = lazy(() => pageModules.operations().then((m) => ({ default: m.Operations })));
const Profile = lazy(() => pageModules.profile().then((m) => ({ default: m.Profile })));
const Reports = lazy(() => pageModules.reports().then((m) => ({ default: m.Reports })));
const Settings = lazy(() => pageModules.settings().then((m) => ({ default: m.Settings })));

/** Once the first screen is up, download the remaining pages in the background so navigation is instant. */
function usePrefetchPages() {
  useEffect(() => {
    if (import.meta.env.MODE === "test") return;
    const prefetch = () => {
      for (const load of Object.values(pageModules)) void load().catch(() => undefined);
    };
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(prefetch, { timeout: 4000 });
      return () => window.cancelIdleCallback(id);
    }
    const id = window.setTimeout(prefetch, 2000);
    return () => window.clearTimeout(id);
  }, []);
}

function HomeRoute() {
  const { can } = useAuth();
  if (can("dashboard:view")) return <Dashboard />;
  if (can("employee:view")) return <Navigate to="/employees" replace />;
  if (can("reports:read")) return <Navigate to="/attendance" replace />;
  return <Navigate to="/profile" replace />;
}

function CapabilityRoute({
  capability,
  children,
}: {
  capability: "forensic_audit";
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  if (!hasCapability(user, capability)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  usePrefetchPages();
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <AppLayout>
              <Suspense fallback={<PageFallback />}>
                <Routes>
                  <Route
                    path="/"
                    element={<HomeRoute />}
                  />
                  <Route
                    path="/employees"
                    element={
                      <RequireAuth permission="employee:view">
                        <Employees />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="/employees/:employeeId"
                    element={
                      <RequireAuth permission="employee:view">
                        <EmployeeProfile />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="/attendance"
                    element={
                      <RequireAuth permission="reports:read">
                        <Attendance />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="/reports"
                    element={
                      <RequireAuth permission="reports:read">
                        <Reports />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="/monitoring"
                    element={
                      <RequireAuth permission="reports:read">
                        <RealtimeMonitoring />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="/operations"
                    element={
                      <RequireAuth permission="device:manage">
                        <Operations />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="/profile"
                    element={<Profile />}
                  />
                  <Route
                    path="/settings"
                    element={
                      <RequireAuth permission="device:manage">
                        <Settings />
                      </RequireAuth>
                    }
                  />
                  <Route
                    path="/audit"
                    element={
                      <CapabilityRoute capability="forensic_audit">
                        <Audit />
                      </CapabilityRoute>
                    }
                  />
                  <Route path="/corrections" element={<Navigate to="/audit" replace />} />
                  <Route path="/raw-attendance" element={<Navigate to="/audit" replace />} />
                  <Route path="/forensics" element={<Navigate to="/audit" replace />} />
                  <Route path="/device-history" element={<Navigate to="/audit" replace />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </AppLayout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
