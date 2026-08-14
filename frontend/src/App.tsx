import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { hasCapability } from "@/features/auth/sessionCapabilities";
import { AppLayout } from "@/components/layout/AppLayout";
import { Attendance } from "@/features/attendance/pages/AttendancePage";
import { Dashboard } from "@/features/dashboard/pages/DashboardPage";
import { EmployeeProfile } from "@/features/employees/pages/EmployeeProfilePage";
import { Employees } from "@/features/employees/pages/EmployeesPage";
import { Login } from "@/features/auth/pages/LoginPage";
import { Operations } from "@/features/operations/pages/OperationsPage";
import { Profile } from "@/features/settings/pages/ProfilePage";
import { Reports } from "@/features/reports/pages/ReportsPage";
import { Audit } from "@/features/audit/pages/AuditPage";
import { Settings } from "@/features/settings/pages/SettingsPage";
import { RealtimeMonitoring } from "@/features/monitoring/pages/RealtimeMonitoringPage";

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
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <AppLayout>
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
                    <RequireAuth permission="metrics:read">
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
            </AppLayout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
