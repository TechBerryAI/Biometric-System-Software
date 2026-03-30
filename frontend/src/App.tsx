import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Attendance } from "./pages/Attendance";
import { Dashboard } from "./pages/Dashboard";
import { Employees } from "./pages/Employees";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/employees" element={<Employees />} />
        <Route path="/attendance" element={<Attendance />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
