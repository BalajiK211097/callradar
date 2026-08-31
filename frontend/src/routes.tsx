import { createBrowserRouter, Navigate } from "react-router";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import AllCalls from "./pages/AllCalls";
import CallDetail from "./pages/CallDetail";
import CustomersList from "./pages/CustomersList";
import CustomerDetail from "./pages/CustomerDetail";
import AgentsList from "./pages/AgentsList";
import AgentDetail from "./pages/AgentDetail";
import Trends from "./pages/Trends";
import Login from "./pages/Login";
import { useAuth } from "./context/AuthContext";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  {
    path: "/login",
    Component: Login,
  },
  {
    path: "/",
    Component: () => (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { index: true, Component: Overview },
      { path: "calls", Component: AllCalls },
      { path: "calls/:callId", Component: CallDetail },
      { path: "customers", Component: CustomersList },
      { path: "customers/:customerId", Component: CustomerDetail },
      { path: "agents", Component: AgentsList },
      { path: "agents/:agentId", Component: AgentDetail },
      { path: "trends", Component: Trends },
      { path: "*", Component: () => <div className="p-8"><p style={{ color: "#94A3B8" }}>Page not found</p></div> },
    ],
  },
]);
