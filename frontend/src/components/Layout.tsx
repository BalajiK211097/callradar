import { useState, useRef, useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { BarChart2, Phone, Users, UserCheck, Bell, Search, ChevronDown, UserCog, Settings, HelpCircle, LogOut, Shield } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { api, type StatsResponse } from "../lib/api";

function RadarIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="2" fill="white" />
      <path d="M12 12 L4 4" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="12" cy="12" r="5" stroke="white" strokeWidth="1.5" opacity="0.7" />
      <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="1.5" opacity="0.35" />
    </svg>
  );
}

const navItems = [
  { to: "/", icon: BarChart2, label: "Overview" },
  { to: "/calls", icon: Phone, label: "All Calls" },
  { to: "/customers", icon: Users, label: "Customers" },
  { to: "/agents", icon: UserCheck, label: "Agents" },
];

function fmtCount(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

export default function Layout() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [search, setSearch] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const [pipelineStats, setPipelineStats] = useState<StatsResponse | null>(null);

  useEffect(() => {
    api.calls.stats().then(setPipelineStats).catch(() => {});
  }, []);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    setProfileOpen(false);
    logout();
    navigate("/login", { replace: true });
  };

  const menuItems = [
    { icon: UserCog, label: "User Management", onClick: () => setProfileOpen(false) },
    { icon: Shield, label: "Permissions", onClick: () => setProfileOpen(false) },
    { icon: Settings, label: "Settings", onClick: () => setProfileOpen(false) },
    { icon: HelpCircle, label: "Help & Support", onClick: () => setProfileOpen(false) },
  ];

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "#F5F7FA" }}>
      {/* ── Sidebar ── */}
      <aside className="w-60 flex-shrink-0 flex flex-col" style={{ background: "#FFFFFF", borderRight: "1px solid #E2E8F0" }}>
        {/* Logo */}
        <div className="h-[60px] flex items-center px-5 gap-3 flex-shrink-0" style={{ borderBottom: "1px solid #E2E8F0" }}>
          <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", boxShadow: "0 2px 8px rgba(99,102,241,0.35)" }}>
            <RadarIcon />
          </div>
          <div>
            <span className="font-bold text-[15px] tracking-tight" style={{ color: "#0F172A" }}>Call Radar</span>
            <span className="text-[9px] block font-mono" style={{ color: "#94A3B8", marginTop: -1 }}>AI · ANALYTICS</span>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider px-3 mb-2" style={{ color: "#CBD5E1" }}>Navigation</p>
          {navItems.map(({ to, icon: Icon, label }) => {
            const badge = to === "/calls" && pipelineStats
              ? fmtCount(pipelineStats.total_calls)
              : undefined;
            return (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className="flex items-center gap-3 px-3 py-2 rounded-lg mb-0.5 text-[13px] font-medium transition-all"
                style={({ isActive }) => ({
                  background: isActive ? "rgba(99,102,241,0.08)" : "transparent",
                  color: isActive ? "#6366F1" : "#64748B",
                  borderLeft: isActive ? "2px solid #6366F1" : "2px solid transparent",
                })}
              >
                {({ isActive }) => (
                  <>
                    <Icon size={15} style={{ flexShrink: 0, opacity: isActive ? 1 : 0.65 }} />
                    <span>{label}</span>
                    {badge && (
                      <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded font-mono"
                        style={{ background: "#F1F5F9", color: "#94A3B8" }}>
                        {badge}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Sidebar footer — live pipeline stats */}
        {(() => {
          const s = pipelineStats;
          const total = s?.total_calls ?? 0;
          const done = s?.done_calls ?? 0;
          const inProgress = (s?.pending_calls ?? 0) + (s?.processing_calls ?? 0);
          const failed = s?.failed_calls ?? 0;
          const pct = total > 0 ? Math.round((done / total) * 100) : 0;
          const allDone = total > 0 && inProgress === 0 && failed === 0 && done === total;
          const barColor = failed > 0 ? "#EF4444" : inProgress > 0 ? "#F59E0B" : "#22C55E";
          const statusText = !s ? "Loading…"
            : allDone ? "All calls processed ✓"
            : inProgress > 0 ? `${inProgress} in progress…`
            : failed > 0 ? `${failed} failed`
            : `${pct}% complete`;

          const rows = [
            { label: "Total calls", value: s ? String(total) : "—", dot: "#6366F1" },
            { label: "Processed",   value: s ? String(done) : "—",  dot: "#22C55E" },
            { label: "In progress", value: s ? String(inProgress) : "—", dot: "#F59E0B" },
            { label: "Failed",      value: s ? String(failed) : "—",     dot: "#EF4444" },
          ];

          return (
            <div className="m-3 rounded-xl overflow-hidden" style={{ background: "#F8FAFC", border: "1px solid #E2E8F0" }}>
              <div className="px-4 py-2.5" style={{ borderBottom: "1px solid #E2E8F0" }}>
                <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "#94A3B8" }}>Pipeline · All time</p>
              </div>
              <div className="px-4 py-3 space-y-2">
                {rows.map(({ label, value, dot }) => (
                  <div key={label} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: dot }} />
                      <span className="text-[12px]" style={{ color: "#94A3B8" }}>{label}</span>
                    </div>
                    <span className="font-mono text-[12px] font-semibold" style={{ color: "#475569" }}>{value}</span>
                  </div>
                ))}
              </div>
              <div className="px-4 pb-3">
                <div className="h-1 rounded-full overflow-hidden" style={{ background: "#E2E8F0" }}>
                  <div className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${pct}%`, background: barColor }} />
                </div>
                <p className="text-[10px] mt-1" style={{ color: "#94A3B8" }}>{statusText}</p>
              </div>
            </div>
          );
        })()}
      </aside>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Navbar */}
        <header className="h-[60px] flex-shrink-0 flex items-center px-6 gap-4"
          style={{ background: "#FFFFFF", borderBottom: "1px solid #E2E8F0" }}>
          <div className="flex-1 max-w-lg relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#CBD5E1" }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search calls, customers, agents..."
              className="w-full pl-9 pr-12 py-2 text-[13px] rounded-lg outline-none transition-colors"
              style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", color: "#0F172A" }}
              onFocus={e => (e.target.style.borderColor = "#6366F1")}
              onBlur={e => (e.target.style.borderColor = "#E2E8F0")}
            />
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] px-1.5 py-0.5 rounded font-mono"
              style={{ background: "#E2E8F0", color: "#94A3B8" }}>⌘K</kbd>
          </div>

          <div className="flex items-center gap-3 ml-auto">
            <button className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-1.5 rounded-lg transition-all hover:bg-slate-50"
              style={{ color: "#64748B", border: "1px solid #E2E8F0" }}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#22C55E" }} />
              Today
              <ChevronDown size={12} />
            </button>
            <button className="relative p-2 rounded-lg hover:bg-slate-50 transition-all" style={{ color: "#64748B" }}>
              <Bell size={15} />
              <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full"
                style={{ background: "#EF4444" }} />
            </button>
            <div ref={profileRef} className="relative flex items-center gap-2.5 pl-3" style={{ borderLeft: "1px solid #E2E8F0" }}>
              <div className="text-right">
                <p className="text-[12px] font-medium" style={{ color: "#0F172A" }}>
                  {user?.name ?? "James Davies"}
                </p>
                <p className="text-[10px]" style={{ color: "#94A3B8" }}>
                  {user?.title ?? "Senior Manager"}
                </p>
              </div>
              <button
                onClick={() => setProfileOpen(o => !o)}
                className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold transition-all hover:brightness-110"
                style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", color: "white" }}
              >
                {user?.initials ?? "JD"}
              </button>

              {profileOpen && (
                <div
                  className="absolute right-0 top-[calc(100%+10px)] w-56 rounded-xl overflow-hidden z-50"
                  style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", boxShadow: "0 8px 24px rgba(15,23,42,0.12)" }}
                >
                  {/* User info header */}
                  <div className="px-4 py-3" style={{ borderBottom: "1px solid #E2E8F0", background: "#F8FAFC" }}>
                    <p className="text-[13px] font-semibold" style={{ color: "#0F172A" }}>{user?.name ?? "James Davies"}</p>
                    <p className="text-[11px]" style={{ color: "#94A3B8" }}>{user?.title ?? "Senior Manager"}</p>
                  </div>

                  {/* Menu items */}
                  <div className="py-1.5">
                    {menuItems.map(({ icon: Icon, label, onClick }) => (
                      <button
                        key={label}
                        onClick={onClick}
                        className="w-full flex items-center gap-2.5 px-4 py-2 text-left text-[13px] transition-colors hover:bg-slate-50"
                        style={{ color: "#475569" }}
                      >
                        <Icon size={14} style={{ flexShrink: 0, color: "#94A3B8" }} />
                        {label}
                      </button>
                    ))}
                  </div>

                  {/* Logout */}
                  <div className="py-1.5" style={{ borderTop: "1px solid #E2E8F0" }}>
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2.5 px-4 py-2 text-left text-[13px] transition-colors hover:bg-red-50"
                      style={{ color: "#DC2626" }}
                    >
                      <LogOut size={14} style={{ flexShrink: 0 }} />
                      Log out
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-auto" style={{ background: "#F5F7FA" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
