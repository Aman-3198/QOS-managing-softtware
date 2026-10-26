import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Devices from "./pages/Devices";
import Rules from "./pages/Rules";
import Analytics from "./pages/Analytics";
import Hotspot from "./pages/Hotspot";
import Diagnostics from "./pages/Diagnostics";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import { useMonitor } from "./hooks/useMonitor";
import { api } from "./api/client";

export default function App() {
  const { snapshot, status } = useMonitor();
  const [auth, setAuth] = useState<{ authenticated: boolean; has_password: boolean } | null>(null);
  const location = useLocation();

  useEffect(() => {
    api.authMe().then(setAuth).catch(() => setAuth({ authenticated: false, has_password: false }));
  }, [location.pathname]);

  // While auth status is unknown, show nothing briefly.
  if (auth === null) return null;

  const needsLogin = auth.has_password && !auth.authenticated;
  const onLogin = location.pathname === "/login";

  return (
    <Routes>
      <Route path="/login" element={needsLogin ? <Login /> : <Navigate to="/" replace />} />
      <Route
        element={
          needsLogin && !onLogin ? <Navigate to="/login" replace /> : <Layout snapshot={snapshot} wsStatus={status} />
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/rules" element={<Rules />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/hotspot" element={<Hotspot />} />
        <Route path="/diagnostics" element={<Diagnostics />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
