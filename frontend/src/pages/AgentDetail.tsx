import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api, type CallSummary, type AgentSummary } from "../lib/api";
import { fmtDuration, fmtTime, fmtRate, initials } from "../lib/format";
import { MomentBadge, ScoreBadge, MoodArc } from "../components/Badges";

const tooltipStyle = {
  backgroundColor: "#FFFFFF", border: "1px solid #E2E8F0",
  borderRadius: "8px", color: "#0F172A", fontSize: "12px",
  boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
};

export default function AgentDetail() {
  const navigate = useNavigate();
  const { agentId } = useParams<{ agentId: string }>();
  const agentName = decodeURIComponent(agentId ?? "");

  const [calls, setCalls] = useState<CallSummary[]>([]);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!agentName) return;
    Promise.all([
      api.agents.calls(agentName, 1),
      api.agents.stats(agentName),
    ]).then(([callsRes, statsRes]) => {
      setCalls(callsRes.items);
      setStats(statsRes);
    }).catch(console.error).finally(() => setLoading(false));
  }, [agentName]);

  const resolutionRate = stats ? (stats.resolution_rate as number ?? 0) : 0;
  const avgScore = stats ? Math.round((stats.avg_attention_score as number) ?? 0) : 0;
  const totalCalls = stats ? (stats.call_count as number ?? 0) : 0;
  const resolvedCount = Math.round(totalCalls * resolutionRate);

  // Simple bar chart data: score distribution across calls
  const scoreBuckets = [0, 0, 0, 0, 0]; // 0-20, 20-40, 40-60, 60-80, 80-100
  calls.forEach(c => {
    const s = c.attention_score ?? 0;
    const bucket = Math.min(4, Math.floor(s / 20));
    scoreBuckets[bucket]++;
  });
  const barData = ["0–20", "20–40", "40–60", "60–80", "80–100"].map((range, i) => ({
    range, count: scoreBuckets[i],
    fill: i < 2 ? "#22C55E" : i < 3 ? "#F59E0B" : "#EF4444",
  }));

  const scoreColor = avgScore >= 80 ? "#EF4444" : avgScore >= 60 ? "#F59E0B" : "#22C55E";
  const rateColor = resolutionRate >= 0.85 ? "#16A34A" : resolutionRate >= 0.75 ? "#D97706" : "#DC2626";

  return (
    <div className="p-6 space-y-5">
      <button onClick={() => navigate("/agents")} className="text-[12px] mb-1"
        style={{ color: "#94A3B8" }}>← Agents</button>

      {loading ? (
        <div className="py-16 text-center text-[13px]" style={{ color: "#94A3B8" }}>Loading…</div>
      ) : (
        <>
          {/* Header card */}
          <div className="card p-6">
            <div className="flex items-center gap-5">
              <div className="w-16 h-16 rounded-full flex items-center justify-center text-[22px] font-bold"
                style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", color: "white" }}>
                {initials(agentName)}
              </div>
              <div className="flex-1">
                <h1 className="text-[24px] font-bold" style={{ color: "#0F172A" }}>{agentName}</h1>
                <p className="text-[13px] mt-0.5" style={{ color: "#94A3B8" }}>{totalCalls} calls processed</p>
              </div>
              <div className="flex gap-4">
                {[
                  { label: "Avg Score", value: String(avgScore), color: scoreColor },
                  { label: "Resolution", value: fmtRate(resolutionRate), color: rateColor },
                  { label: "Handle Time", value: fmtDuration(stats?.avg_handle_time as number), color: "#64748B" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="text-center px-4 py-3 rounded-xl" style={{ background: "#F8FAFC", border: "1px solid #E2E8F0" }}>
                    <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#94A3B8" }}>{label}</p>
                    <p className="font-bold text-[20px]" style={{ color }}>{value}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-5" style={{ gridTemplateColumns: "1fr 1fr" }}>
            {/* Score distribution */}
            <div className="card p-5">
              <h3 className="font-semibold text-[14px] mb-4" style={{ color: "#0F172A" }}>Attention Score Distribution</h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={barData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="range" tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#F8FAFC" }} />
                  <Bar dataKey="count" name="Calls" radius={[4, 4, 0, 0]}
                    fill="#6366F1" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Stats grid */}
            <div className="card p-5">
              <h3 className="font-semibold text-[14px] mb-4" style={{ color: "#0F172A" }}>Performance Summary</h3>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "Total Calls", value: String(totalCalls), color: "#0F172A" },
                  { label: "Resolved", value: String(resolvedCount), color: "#16A34A" },
                  { label: "Resolution Rate", value: fmtRate(resolutionRate), color: rateColor },
                  { label: "Avg Attn. Score", value: String(avgScore), color: scoreColor },
                ].map(({ label, value, color }) => (
                  <div key={label} className="rounded-xl p-3" style={{ background: "#F8FAFC", border: "1px solid #F1F5F9" }}>
                    <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#94A3B8" }}>{label}</p>
                    <p className="font-bold text-[22px]" style={{ color }}>{value}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Recent calls */}
          <div className="card overflow-hidden">
            <div className="px-5 py-4" style={{ borderBottom: "1px solid #F1F5F9" }}>
              <h2 className="font-semibold text-[15px]" style={{ color: "#0F172A" }}>Recent Calls</h2>
            </div>
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: "1px solid #F1F5F9", background: "#FAFBFC" }}>
                  {["Time", "Customer", "Duration", "Intent", "Mood", "Score", "Resolved"].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: "#94A3B8" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {calls.length === 0 ? (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-[13px]" style={{ color: "#94A3B8" }}>No calls found</td></tr>
                ) : calls.slice(0, 20).map((call, i) => (
                  <tr key={call.call_id}
                    onClick={() => navigate(`/calls/${call.call_id}`)}
                    className="cursor-pointer"
                    style={{ borderBottom: "1px solid #F8FAFC", background: i % 2 === 0 ? "transparent" : "#FAFBFC" }}
                    onMouseEnter={e => (e.currentTarget.style.background = "#F0F1FF")}
                    onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "#FAFBFC")}>
                    <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>
                      {fmtTime(call.call_start_utc ?? call.created_at)}
                    </td>
                    <td className="px-4 py-3 text-[13px] font-medium" style={{ color: "#0F172A" }}>{call.customer_name ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>{fmtDuration(call.duration_seconds)}</td>
                    <td className="px-4 py-3 max-w-[160px]">
                      <span className="text-[12px] truncate block" style={{ color: "#64748B" }}>{call.intent ?? "—"}</span>
                    </td>
                    <td className="px-4 py-3"><MoodArc startScore={call.mood_start ?? 0} endScore={call.mood_end ?? 0} /></td>
                    <td className="px-4 py-3"><ScoreBadge score={call.attention_score ?? 0} /></td>
                    <td className="px-4 py-3 text-[12px]" style={{ color: call.resolved ? "#22C55E" : "#EF4444" }}>
                      {call.resolved ? "✅" : "❌"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
