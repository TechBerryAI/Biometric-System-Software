import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { RequireAuth } from "@/auth/RequireAuth";
import { AppLayout } from "@/components/layout/AppLayout";
import { Attendance } from "@/pages/Attendance";
import { Dashboard } from "@/pages/Dashboard";
import { EmployeeProfile } from "@/pages/EmployeeProfile";
import { Employees } from "@/pages/Employees";
import { Login } from "@/pages/Login";
import { Operations } from "@/pages/Operations";
import { Profile } from "@/pages/Profile";
import { Reports } from "@/pages/Reports";
import { Audit } from "@/pages/Audit";
import { Settings } from "@/pages/Settings";
import { isPrivilegedAccount } from "@/auth/privilegedAccess";

function HomeRoute() {
  const { can } = useAuth();
  if (can("dashboard:view")) return <Dashboard />;
  if (can("employee:view")) return <Navigate to="/employees" replace />;
  if (can("reports:read")) return <Navigate to="/attendance" replace />;
  return <Navigate to="/profile" replace />;
}

function PrivilegedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!isPrivilegedAccount(user)) {
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
                    <RequireAuth permission="anomaly:manage">
                      <Reports />
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
                    <PrivilegedRoute>
                      <Audit />
                    </PrivilegedRoute>
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
