import { useState, useEffect } from "react";
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { api, type TrendDay, type TrendingIntent } from "../lib/api";

const tooltipStyle = {
  backgroundColor: "#FFFFFF",
  border: "1px solid #E2E8F0",
  borderRadius: "8px",
  color: "#0F172A",
  fontSize: "12px",
  boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
};

const wordCloudWords = [
  { text: "card blocked", size: 28, color: "#EF4444" },
  { text: "payment failed", size: 24, color: "#F59E0B" },
  { text: "fraud", size: 20, color: "#EF4444" },
  { text: "unresolved", size: 18, color: "#F59E0B" },
  { text: "ATM", size: 22, color: "#EAB308" },
  { text: "manager", size: 16, color: "#A855F7" },
  { text: "transfer", size: 14, color: "#6366F1" },
  { text: "account access", size: 18, color: "#F59E0B" },
  { text: "PIN", size: 20, color: "#EAB308" },
  { text: "refund", size: 14, color: "#6366F1" },
  { text: "frustrated", size: 16, color: "#EF4444" },
  { text: "mortgage", size: 12, color: "#64748B" },
  { text: "loan", size: 12, color: "#64748B" },
  { text: "direct debit", size: 14, color: "#6366F1" },
];

export default function Trends() {
  const [range, setRange] = useState<7 | 14 | 30>(30);
  const [trendData, setTrendData] = useState<TrendDay[]>([]);
  const [intents, setIntents] = useState<TrendingIntent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.calls.trends(range),
      api.calls.trendingIntents(12),
    ]).then(([trends, topIntents]) => {
      setTrendData(trends);
      setIntents(topIntents);
    }).catch(console.error).finally(() => setLoading(false));
  }, [range]);

  const fmtDate = (iso: string) => {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-bold" style={{ color: "#0F172A" }}>Trends</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "#94A3B8" }}>Call patterns and volume over time</p>
        </div>
        <div className="flex gap-1 p-1 rounded-lg" style={{ background: "#F1F5F9" }}>
          {([7, 14, 30] as const).map(d => (
            <button key={d} onClick={() => setRange(d)}
              className="text-[12px] px-3 py-1.5 rounded-md font-medium"
              style={{ background: range === d ? "#6366F1" : "transparent", color: range === d ? "white" : "#94A3B8" }}>
              {d}d
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-[13px]" style={{ color: "#94A3B8" }}>Loading trends…</div>
      ) : (
        <>
          {/* Volume + resolution chart */}
          <div className="card p-5">
            <h2 className="font-semibold text-[15px] mb-5" style={{ color: "#0F172A" }}>Call Volume & Resolution Rate</h2>
            {trendData.length === 0 ? (
              <p className="text-[13px] text-center py-8" style={{ color: "#94A3B8" }}>No trend data yet</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={trendData.map(d => ({ ...d, date: fmtDate(d.date), resolution_pct: Math.round(d.resolution_rate * 100) }))}
                  margin={{ top: 8, right: 20, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6366F1" stopOpacity={0.2} />
                      <stop offset="100%" stopColor="#6366F1" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="resGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#22C55E" stopOpacity={0.2} />
                      <stop offset="100%" stopColor="#22C55E" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="date" tick={{ fill: "#CBD5E1", fontSize: 11 }} axisLine={{ stroke: "#E2E8F0" }} tickLine={false} />
                  <YAxis yAxisId="left" tick={{ fill: "#CBD5E1", fontSize: 11 }} axisLine={{ stroke: "#E2E8F0" }} tickLine={false} />
                  <YAxis yAxisId="right" orientation="right"
                    tick={{ fill: "#CBD5E1", fontSize: 11 }} axisLine={false} tickLine={false}
                    tickFormatter={v => `${v}%`} domain={[0, 100]} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend />
                  <Area yAxisId="left" type="monotone" dataKey="call_count" name="Calls"
                    stroke="#6366F1" strokeWidth={2.5} fill="url(#volGrad)" dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="resolution_pct" name="Resolution %"
                    stroke="#22C55E" strokeWidth={2} dot={false} strokeDasharray="4 3" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="grid gap-5" style={{ gridTemplateColumns: "3fr 2fr" }}>
            {/* Avg attention score trend */}
            <div className="card p-5">
              <h2 className="font-semibold text-[15px] mb-5" style={{ color: "#0F172A" }}>Avg Attention Score</h2>
              {trendData.length === 0 ? (
                <p className="text-[13px] text-center py-8" style={{ color: "#94A3B8" }}>No data</p>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={trendData.map(d => ({ ...d, date: fmtDate(d.date) }))}
                    margin={{ top: 8, right: 20, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                    <XAxis dataKey="date" tick={{ fill: "#CBD5E1", fontSize: 11 }} axisLine={{ stroke: "#E2E8F0" }} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={{ fill: "#CBD5E1", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="avg_score" name="Avg Score"
                      stroke="#F59E0B" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Top intents */}
            <div className="card p-5">
              <h2 className="font-semibold text-[15px] mb-5" style={{ color: "#0F172A" }}>Top Intents</h2>
              <div className="space-y-2.5">
                {intents.slice(0, 6).map((intent, i) => {
                  const max = intents[0]?.count ?? 1;
                  const pct = (intent.count / max) * 100;
                  return (
                    <div key={i} className="flex items-center gap-3">
                      <span className="text-[12px] w-[120px] flex-shrink-0 truncate" style={{ color: "#64748B" }}
                        title={intent.intent}>{intent.intent || "—"}</span>
                      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: "#F1F5F9" }}>
                        <div className="h-full rounded-full"
                          style={{ width: `${pct}%`, background: i < 2 ? "#EF4444" : i < 4 ? "#F59E0B" : "#6366F1" }} />
                      </div>
                      <span className="font-mono text-[12px] font-semibold w-8 text-right" style={{ color: "#0F172A" }}>
                        {intent.count}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Word cloud (static — derived from top intents) */}
          <div className="card p-5">
            <h2 className="font-semibold text-[15px] mb-5" style={{ color: "#0F172A" }}>Topic Word Cloud</h2>
            <div className="flex flex-wrap gap-3 justify-center py-4">
              {wordCloudWords.map(word => (
                <span key={word.text} className="cursor-default select-none font-semibold rounded-lg px-3 py-1.5"
                  style={{ fontSize: word.size / 2.2 + "px", color: word.color, background: `${word.color}10`, border: `1px solid ${word.color}20` }}>
                  {word.text}
                </span>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
