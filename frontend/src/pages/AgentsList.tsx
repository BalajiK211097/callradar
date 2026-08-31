import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { TrendingDown, TrendingUp, ChevronRight, Search, ChevronLeft } from "lucide-react";
import { api, type AgentSummary } from "../lib/api";
import { fmtDuration, fmtRate, initials } from "../lib/format";

const PAGE_SIZE = 10;

const avatarColors = [
  "linear-gradient(135deg, #6366F1, #4F46E5)",
  "linear-gradient(135deg, #0EA5E9, #0284C7)",
  "linear-gradient(135deg, #10B981, #059669)",
  "linear-gradient(135deg, #F59E0B, #D97706)",
  "linear-gradient(135deg, #EF4444, #DC2626)",
  "linear-gradient(135deg, #8B5CF6, #7C3AED)",
];

export default function AgentsList() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.agents.list()
      .then(setAgents)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // Reset to page 1 whenever search changes
  useEffect(() => { setPage(1); }, [search]);

  const filtered = agents.filter(a =>
    !search || a.agent_name.toLowerCase().includes(search.toLowerCase())
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const avgResolution = agents.length
    ? Math.round(agents.reduce((s, a) => s + a.resolution_rate, 0) / agents.length * 100)
    : 0;

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-[22px] font-bold" style={{ color: "#0F172A" }}>Agents</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "#94A3B8" }}>
            {loading ? "Loading…" : `${filtered.length} of ${agents.length} agents · all-time performance`}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#CBD5E1" }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search agents..."
              className="pl-9 pr-4 py-2 text-[13px] rounded-lg outline-none w-52"
              style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", color: "#0F172A" }}
            />
          </div>
          {/* Stats chips */}
          {[
            { label: "Total Calls", value: agents.reduce((s, a) => s + a.call_count, 0).toLocaleString() },
            { label: "Avg Resolution", value: `${avgResolution}%` },
          ].map(({ label, value }) => (
            <div key={label} className="card px-4 py-2 text-center">
              <p className="text-[10px] uppercase tracking-wider" style={{ color: "#94A3B8" }}>{label}</p>
              <p className="font-bold text-[16px]" style={{ color: "#0F172A" }}>{value}</p>
            </div>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-[13px]" style={{ color: "#94A3B8" }}>Loading agents…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-[15px] font-medium" style={{ color: "#94A3B8" }}>No agents match "{search}"</p>
          <button onClick={() => setSearch("")} className="text-[13px] mt-2" style={{ color: "#6366F1" }}>
            Clear search
          </button>
        </div>
      ) : (
        <>
          {/* Grid */}
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
            {paginated.map((agent, i) => {
              const globalIdx = (page - 1) * PAGE_SIZE + i;
              const score = agent.avg_attention_score ?? 0;
              const scoreColor = score < 30 ? "#16A34A" : score < 50 ? "#D97706" : "#DC2626";
              const scoreBg   = score < 30 ? "#F0FDF4" : score < 50 ? "#FEF3C7" : "#FEF2F2";
              const scoreBorder = score < 30 ? "#BBF7D0" : score < 50 ? "#FDE68A" : "#FECACA";
              const rateColor = agent.resolution_rate >= 0.85 ? "#16A34A" : agent.resolution_rate >= 0.75 ? "#D97706" : "#DC2626";

              return (
                <div
                  key={agent.agent_name}
                  onClick={() => navigate(`/agents/${encodeURIComponent(agent.agent_name)}`)}
                  className="card p-5 cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 group"
                >
                  {/* Top */}
                  <div className="flex items-center gap-4 mb-5">
                    <div
                      className="w-12 h-12 rounded-xl flex items-center justify-center text-[16px] font-bold flex-shrink-0 text-white"
                      style={{ background: avatarColors[globalIdx % avatarColors.length] }}
                    >
                      {initials(agent.agent_name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-[15px]" style={{ color: "#0F172A" }}>{agent.agent_name}</p>
                      <p className="text-[12px]" style={{ color: "#94A3B8" }}>—</p>
                    </div>
                    <div className="text-center">
                      <p className="text-[10px] uppercase tracking-wider mb-0.5" style={{ color: "#94A3B8" }}>Score</p>
                      <span className="font-mono font-bold text-[14px] px-2.5 py-0.5 rounded-lg"
                        style={{ background: scoreBg, color: scoreColor, border: `1px solid ${scoreBorder}` }}>
                        {score}
                      </span>
                    </div>
                  </div>

                  {/* Stats grid */}
                  <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="rounded-xl p-3" style={{ background: "#F8FAFC", border: "1px solid #F1F5F9" }}>
                      <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#94A3B8" }}>Total Calls</p>
                      <p className="font-bold text-[20px]" style={{ color: "#0F172A" }}>{agent.call_count}</p>
                      <p className="text-[11px]" style={{ color: "#94A3B8" }}>all time</p>
                    </div>
                    <div className="rounded-xl p-3" style={{ background: "#F8FAFC", border: "1px solid #F1F5F9" }}>
                      <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#94A3B8" }}>Resolution Rate</p>
                      <p className="font-bold text-[20px]" style={{ color: rateColor }}>{fmtRate(agent.resolution_rate)}</p>
                      <div className="flex items-center gap-1 text-[11px]" style={{ color: "#94A3B8" }}>
                        {agent.resolution_rate >= 0.8
                          ? <TrendingUp size={11} style={{ color: "#22C55E" }} />
                          : <TrendingDown size={11} style={{ color: "#EF4444" }} />}
                        vs avg
                      </div>
                    </div>
                    <div className="rounded-xl p-3" style={{ background: "#F8FAFC", border: "1px solid #F1F5F9" }}>
                      <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#94A3B8" }}>Avg Handle Time</p>
                      <p className="font-bold text-[20px] font-mono" style={{ color: "#0F172A" }}>
                        {fmtDuration(agent.avg_handle_time)}
                      </p>
                      <p className="text-[11px]" style={{ color: "#94A3B8" }}>mm:ss per call</p>
                    </div>
                    <div className="rounded-xl p-3" style={{ background: "#F8FAFC", border: "1px solid #F1F5F9" }}>
                      <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#94A3B8" }}>Avg Attn. Score</p>
                      <p className="font-bold text-[20px]" style={{ color: scoreColor }}>{score}</p>
                      <p className="text-[11px]" style={{ color: "#94A3B8" }}>lower is better</p>
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div className="mb-4">
                    <div className="flex justify-between text-[10px] mb-1" style={{ color: "#94A3B8" }}>
                      <span>Resolution rate</span>
                      <span style={{ color: rateColor }}>{fmtRate(agent.resolution_rate)}</span>
                    </div>
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "#F1F5F9" }}>
                      <div className="h-full rounded-full transition-all"
                        style={{ width: `${Math.round(agent.resolution_rate * 100)}%`, background: rateColor }} />
                    </div>
                  </div>

                  {/* Footer */}
                  <div className="flex items-center justify-between pt-3" style={{ borderTop: "1px solid #F1F5F9" }}>
                    <p className="text-[12px]" style={{ color: "#94A3B8" }}>QA avg: {agent.avg_qa_score ?? "—"}</p>
                    <span className="flex items-center gap-1 text-[12px] font-medium opacity-0 group-hover:opacity-100 transition-all"
                      style={{ color: "#6366F1" }}>
                      View profile <ChevronRight size={13} />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-[13px]" style={{ color: "#94A3B8" }}>
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-all disabled:opacity-40"
                  style={{ background: "#F1F5F9", color: "#475569" }}
                >
                  <ChevronLeft size={14} /> Prev
                </button>
                <div className="flex items-center gap-1">
                  {Array.from({ length: totalPages }, (_, i) => i + 1)
                    .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                    .reduce<(number | "…")[]>((acc, p, idx, arr) => {
                      if (idx > 0 && (arr[idx - 1] as number) < p - 1) acc.push("…");
                      acc.push(p);
                      return acc;
                    }, [])
                    .map((item, idx) =>
                      item === "…" ? (
                        <span key={`ellipsis-${idx}`} className="px-1 text-[13px]" style={{ color: "#94A3B8" }}>…</span>
                      ) : (
                        <button
                          key={item}
                          onClick={() => setPage(item as number)}
                          className="w-8 h-8 rounded-lg text-[13px] font-medium transition-all"
                          style={{
                            background: page === item ? "#6366F1" : "#F1F5F9",
                            color: page === item ? "#FFFFFF" : "#475569",
                          }}
                        >
                          {item}
                        </button>
                      )
                    )}
                </div>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-all disabled:opacity-40"
                  style={{ background: "#F1F5F9", color: "#475569" }}
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
