import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import LoginPage from "@/pages/LoginPage";
import SystemLayout from "@/components/SystemLayout";
import Dashboard from "@/pages/Dashboard";
import InventoryPage from "@/pages/InventoryPage";
import BorrowPage from "@/pages/BorrowPage";
import SettingsPage from "@/pages/SettingsPage";
import StockInPage from "@/pages/StockInPage";
import DataDashboard from "@/pages/DataDashboard";
import QueryPage from "@/pages/QueryPage";
import ChemicalInfoPage from "@/pages/ChemicalInfoPage";
import ControlledListPage from "@/pages/ControlledListPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/" element={<ProtectedRoute><SystemLayout /></ProtectedRoute>}>
        <Route index element={<Dashboard />} />
        <Route path="inventory" element={<InventoryPage />} />
        <Route path="borrow" element={<BorrowPage />} />
        <Route path="stock-in" element={<StockInPage />} />
        <Route path="dashboard" element={<DataDashboard />} />
        <Route path="query" element={<QueryPage />} />
        <Route path="chemical-info" element={<ChemicalInfoPage />} />
        <Route path="controlled-list" element={<ControlledListPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
