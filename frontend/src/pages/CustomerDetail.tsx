import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Phone, ArrowRight } from "lucide-react";
import { api, type CallSummary } from "../lib/api";
import { fmtDuration, fmtTime, fmtRate, initials } from "../lib/format";
import { MomentBadge, ScoreBadge, RiskBadge, MoodArc } from "../components/Badges";

export default function CustomerDetail() {
  const navigate = useNavigate();
  const { customerId } = useParams<{ customerId: string }>();
  const customerName = decodeURIComponent(customerId ?? "");

  const [calls, setCalls] = useState<CallSummary[]>([]);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!customerName) return;
    Promise.all([
      api.customers.calls(customerName, 1),
      api.customers.profile(customerName),
    ]).then(([callsRes, profileRes]) => {
      setCalls(callsRes.items);
      setProfile(profileRes);
    }).catch(console.error).finally(() => setLoading(false));
  }, [customerName]);

  const totalCalls = calls.length;
  const resolvedCount = calls.filter(c => c.resolved).length;
  const resolutionRate = totalCalls ? resolvedCount / totalCalls : 0;
  const avgScore = totalCalls
    ? Math.round(calls.reduce((s, c) => s + (c.attention_score ?? 0), 0) / totalCalls)
    : 0;
  const riskLevel = profile?.risk_level as string ?? "LOW";

  return (
    <div className="p-6 space-y-5">
      <button onClick={() => navigate("/customers")} className="text-[12px] mb-1"
        style={{ color: "#94A3B8" }}>← Customers</button>

      {loading ? (
        <div className="py-16 text-center text-[13px]" style={{ color: "#94A3B8" }}>Loading…</div>
      ) : (
        <>
          {/* Header card */}
          <div className="card p-6">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-5">
                <div className="w-16 h-16 rounded-full flex items-center justify-center text-[22px] font-bold flex-shrink-0"
                  style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", color: "white" }}>
                  {initials(customerName)}
                </div>
                <div>
                  <h1 className="text-[24px] font-bold" style={{ color: "#0F172A" }}>{customerName}</h1>
                  <div className="flex items-center gap-4 mt-1">
                    <span className="flex items-center gap-1.5 text-[13px]" style={{ color: "#94A3B8" }}>
                      <Phone size={13} /> —
                    </span>
                  </div>
                </div>
              </div>
              <RiskBadge level={riskLevel} />
            </div>

            <div className="grid grid-cols-4 gap-4 mt-5">
              {[
                { label: "Total Calls", value: String(totalCalls), color: "#0F172A" },
                { label: "Resolved", value: `${resolvedCount}/${totalCalls}`, color: "#16A34A" },
                { label: "Resolution Rate", value: fmtRate(resolutionRate), color: resolutionRate >= 0.8 ? "#16A34A" : "#D97706" },
                { label: "Avg Attn Score", value: String(avgScore), color: avgScore >= 60 ? "#EF4444" : "#22C55E" },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-xl p-4 text-center" style={{ background: "#F8FAFC", border: "1px solid #E2E8F0" }}>
                  <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "#94A3B8" }}>{label}</p>
                  <p className="font-bold text-[22px]" style={{ color }}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Call history */}
          <div className="card overflow-hidden">
            <div className="px-5 py-4" style={{ borderBottom: "1px solid #F1F5F9" }}>
              <h2 className="font-semibold text-[15px]" style={{ color: "#0F172A" }}>Call History</h2>
            </div>
            <div className="space-y-3 p-4">
              {calls.length === 0 ? (
                <p className="text-center py-8 text-[13px]" style={{ color: "#94A3B8" }}>No calls found</p>
              ) : calls.map(call => (
                <div key={call.call_id}
                  className="flex items-center gap-4 rounded-xl p-4 cursor-pointer"
                  style={{ background: "#FAFBFC", border: "1px solid #E2E8F0" }}
                  onClick={() => navigate(`/calls/${call.call_id}`)}
                  onMouseEnter={e => (e.currentTarget.style.background = "#F0F1FF")}
                  onMouseLeave={e => (e.currentTarget.style.background = "#FAFBFC")}>
                  <div className="flex-shrink-0 text-center w-16">
                    <p className="font-mono text-[11px]" style={{ color: "#94A3B8" }}>
                      {fmtTime(call.call_start_utc ?? call.created_at)}
                    </p>
                    <p className="font-mono text-[11px]" style={{ color: "#CBD5E1" }}>
                      {fmtDuration(call.duration_seconds)}
                    </p>
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-medium truncate" style={{ color: "#0F172A" }}>
                      {call.intent ?? "—"}
                    </p>
                    <p className="text-[12px]" style={{ color: "#94A3B8" }}>
                      Agent: {call.agent_name ?? "—"}
                    </p>
                  </div>

                  <MoodArc startScore={call.mood_start ?? 0} endScore={call.mood_end ?? 0} />

                  <div className="flex items-center gap-2">
                    {call.top_moment_type && <MomentBadge type={call.top_moment_type} small />}
                    <ScoreBadge score={call.attention_score ?? 0} />
                    <span className="text-[12px]" style={{ color: call.resolved ? "#22C55E" : "#EF4444" }}>
                      {call.resolved ? "✅" : "❌"}
                    </span>
                  </div>

                  <ArrowRight size={14} style={{ color: "#CBD5E1", flexShrink: 0 }} />
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
