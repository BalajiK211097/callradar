import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { Search, X, ChevronLeft, ChevronRight } from "lucide-react";
import { api, type CallSummary } from "../lib/api";
import { fmtDuration, fmtTime } from "../lib/format";
import { MomentBadge, ScoreBadge, MoodArc } from "../components/Badges";

const PAGE_SIZE = 50;

export default function AllCalls() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<CallSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [agentNames, setAgentNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.calls
      .list({ page, page_size: PAGE_SIZE, status: "done" })
      .then(res => {
        setItems(res.items);
        setTotal(res.total);
        setAgentNames(prev => {
          const names = new Set([...prev, ...res.items.map(c => c.agent_name ?? "").filter(Boolean)]);
          return [...names].sort();
        });
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page]);

  const filtered = items.filter(c => {
    if (search && !c.customer_name?.toLowerCase().includes(search.toLowerCase())) return false;
    if (agentFilter && c.agent_name !== agentFilter) return false;
    if (statusFilter === "resolved" && !c.resolved) return false;
    if (statusFilter === "unresolved" && c.resolved) return false;
    return true;
  });

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const selectStyle = {
    background: "#FFFFFF",
    border: "1px solid #E2E8F0",
    color: "#64748B",
    borderRadius: 8,
    padding: "6px 12px",
    fontSize: 13,
    outline: "none",
    cursor: "pointer",
  };

  return (
    <div className="p-6 space-y-4">
      {/* Filter bar */}
      <div className="card px-4 py-3 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#CBD5E1" }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by customer name..."
            className="w-full pl-8 pr-3 py-1.5 text-[13px] rounded-lg outline-none"
            style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", color: "#0F172A" }}
          />
        </div>
        <select value={agentFilter} onChange={e => setAgentFilter(e.target.value)} style={selectStyle}>
          <option value="">All Agents</option>
          {agentNames.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={selectStyle}>
          <option value="">All Status</option>
          <option value="resolved">Resolved</option>
          <option value="unresolved">Unresolved</option>
        </select>
        {(search || agentFilter || statusFilter) && (
          <button
            onClick={() => { setSearch(""); setAgentFilter(""); setStatusFilter(""); }}
            className="flex items-center gap-1 text-[12px] transition-all hover:opacity-70"
            style={{ color: "#6366F1" }}
          >
            <X size={13} /> Clear filters
          </button>
        )}
        <div className="ml-auto text-[12px]" style={{ color: "#94A3B8" }}>
          {loading ? "Loading…" : `${filtered.length} shown · ${total.toLocaleString()} total`}
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid #F1F5F9", background: "#FAFBFC" }}>
              {["Call ID", "Customer", "Agent", "Time", "Duration", "Intent", "Mood", "Resolved", "Score", "Moments", "Action"].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#94A3B8" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={11} className="px-4 py-8 text-center text-[13px]" style={{ color: "#94A3B8" }}>Loading calls…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={11} className="px-4 py-8 text-center text-[13px]" style={{ color: "#94A3B8" }}>No calls found</td></tr>
            ) : filtered.map((call, i) => (
              <tr
                key={call.call_id}
                onClick={() => navigate(`/calls/${call.call_id}`)}
                className="cursor-pointer group transition-all"
                style={{
                  borderBottom: "1px solid #F8FAFC",
                  background: i % 2 === 0 ? "transparent" : "#FAFBFC",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "#F0F1FF")}
                onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "#FAFBFC")}
              >
                <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#CBD5E1" }}>#{call.call_id.slice(0, 8)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                      style={{ background: "linear-gradient(135deg,#6366F1,#4F46E5)", color: "white" }}>
                      {(call.customer_name ?? "?").split(" ").map(n => n[0]).join("").slice(0, 2)}
                    </div>
                    <span className="text-[13px] font-medium" style={{ color: "#0F172A" }}>{call.customer_name ?? "—"}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-[13px]" style={{ color: "#64748B" }}>{call.agent_name ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>
                  {fmtTime(call.call_start_utc ?? call.created_at)}
                </td>
                <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>
                  {fmtDuration(call.duration_seconds)}
                </td>
                <td className="px-4 py-3 max-w-[180px]">
                  <span className="text-[13px] block truncate" style={{ color: "#64748B" }} title={call.intent ?? ""}>
                    {call.intent ?? "—"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <MoodArc startScore={call.mood_start ?? 0} endScore={call.mood_end ?? 0} />
                </td>
                <td className="px-4 py-3">
                  {call.resolved
                    ? <span className="text-[12px] font-medium" style={{ color: "#22C55E" }}>✅ Resolved</span>
                    : <span className="text-[12px] font-medium" style={{ color: "#EF4444" }}>❌ Unresolved</span>
                  }
                </td>
                <td className="px-4 py-3"><ScoreBadge score={call.attention_score ?? 0} /></td>
                <td className="px-4 py-3">
                  <div className="flex gap-1 flex-wrap">
                    {call.moment_types.slice(0, 2).map(m => <MomentBadge key={m} type={m} small />)}
                    {call.moment_types.length > 2 && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded" style={{ color: "#94A3B8", background: "#F1F5F9" }}>
                        +{call.moment_types.length - 2}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <button
                    className="text-[12px] font-medium px-3 py-1 rounded-md transition-all opacity-0 group-hover:opacity-100"
                    style={{ background: "rgba(99,102,241,0.1)", color: "#6366F1", border: "1px solid rgba(99,102,241,0.25)" }}
                  >
                    View →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: "1px solid #F1F5F9" }}>
          <span className="text-[12px]" style={{ color: "#94A3B8" }}>
            Page {page} of {totalPages} · {total.toLocaleString()} calls
          </span>
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              className="p-1.5 rounded transition-all hover:bg-slate-50 disabled:opacity-30"
              style={{ color: "#CBD5E1" }}
            >
              <ChevronLeft size={14} />
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const p = page <= 3 ? i + 1 : page - 2 + i;
              if (p < 1 || p > totalPages) return null;
              return (
                <button key={p}
                  onClick={() => setPage(p)}
                  className="px-2.5 py-1 rounded text-[12px] transition-all font-medium"
                  style={{
                    background: p === page ? "#6366F1" : "transparent",
                    color: p === page ? "white" : "#94A3B8",
                  }}>{p}</button>
              );
            })}
            <button
              disabled={page >= totalPages}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              className="p-1.5 rounded transition-all hover:bg-slate-50 disabled:opacity-30"
              style={{ color: "#64748B" }}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
