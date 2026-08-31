import { useNavigate } from "react-router";
import { useRef, useState, useCallback, useEffect, useMemo } from "react";
import {
  ArrowUpRight, ChevronRight, ChevronLeft, AlertTriangle,
  Upload, FileAudio, CheckCircle, X, ShieldAlert, TrendingUp, TrendingDown,
} from "lucide-react";
import { api, type CallSummary, type StatsResponse, type TrendingIntent, type AgentSummary } from "../lib/api";
import { fmtDuration, fmtTime, initials } from "../lib/format";
import { MomentBadge, ScoreBadge } from "../components/Badges";

// ── Upload Widget ─────────────────────────────────────────────────────────────

type UploadStage = "idle" | "uploading" | "transcribing" | "analysing" | "done" | "error";
const STAGE_LABELS: Record<UploadStage, string> = {
  idle: "",
  uploading: "Uploading audio…",
  transcribing: "Transcribing with Deepgram…",
  analysing: "Running AI analysis…",
  done: "Analysis complete!",
  error: "",
};

function UploadWidget() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const animRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [stage, setStage] = useState<UploadStage>("idle");
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [callId, setCallId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const clearTimers = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (animRef.current) { clearInterval(animRef.current); animRef.current = null; }
  }, []);

  const crawlTo = useCallback((target: number, intervalMs: number) => {
    if (animRef.current) clearInterval(animRef.current);
    animRef.current = setInterval(() => {
      setProgress(p => {
        if (p >= target) { clearInterval(animRef.current!); animRef.current = null; return p; }
        return Math.min(p + 0.5, target);
      });
    }, intervalMs);
  }, []);

  const startPolling = useCallback((id: string) => {
    setStage("transcribing");
    crawlTo(55, 200);
    let elapsed = 0;
    let inAnalysing = false;
    pollRef.current = setInterval(async () => {
      elapsed += 3;
      try {
        const detail = await api.calls.detail(id);
        if (detail.status === "done") {
          clearTimers();
          setProgress(100);
          setStage("done");
          setCallId(id);
        } else if (detail.status === "failed") {
          clearTimers();
          setErrorMsg(detail.analysis ? "Pipeline failed." : "Pipeline failed — check server logs.");
          setStage("error");
        } else if (elapsed >= 45 && !inAnalysing) {
          inAnalysing = true;
          setStage("analysing");
          crawlTo(90, 400);
        }
      } catch {
        // ignore transient poll errors
      }
    }, 3000);
  }, [clearTimers, crawlTo]);

  const handleFile = useCallback(async (file: File) => {
    if (!file.type.startsWith("audio/") && !file.name.endsWith(".mp3") && !file.name.endsWith(".wav")) return;
    clearTimers();
    setFileName(file.name);
    setStage("uploading");
    setProgress(0);
    setErrorMsg("");
    setCallId(null);
    crawlTo(20, 80);

    try {
      const result = await api.calls.upload(file);
      if (animRef.current) { clearInterval(animRef.current); animRef.current = null; }
      setProgress(22);
      startPolling(result.call_id);
    } catch (err) {
      clearTimers();
      setErrorMsg(err instanceof Error ? err.message : "Upload failed.");
      setStage("error");
    }
  }, [clearTimers, crawlTo, startPolling]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0]; if (f) handleFile(f);
  };
  const reset = () => { clearTimers(); setStage("idle"); setProgress(0); setFileName(""); setCallId(null); setErrorMsg(""); };

  const isIdle = stage === "idle", isDone = stage === "done", isError = stage === "error";

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-5 h-5 rounded-md flex items-center justify-center"
          style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}>
          <Upload size={11} color="white" />
        </div>
        <h3 className="font-semibold text-[14px]" style={{ color: "#0F172A" }}>Analyse a Call</h3>
        <span className="text-[11px] px-2 py-0.5 rounded-full ml-1"
          style={{ background: "#EEF2FF", color: "#6366F1", border: "1px solid #C7D2FE" }}>MP3 / WAV</span>
      </div>

      {isIdle ? (
        <div onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
          onDrop={handleDrop} onClick={() => inputRef.current?.click()}
          className="rounded-xl border-2 border-dashed cursor-pointer flex flex-col items-center justify-center gap-2 py-8"
          style={{ borderColor: dragging ? "#6366F1" : "#E2E8F0", background: dragging ? "#EEF2FF" : "#F8FAFC" }}>
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: dragging ? "#EEF2FF" : "#F1F5F9" }}>
            <FileAudio size={20} style={{ color: dragging ? "#6366F1" : "#CBD5E1" }} />
          </div>
          <div className="text-center">
            <p className="text-[13px] font-medium" style={{ color: "#64748B" }}>
              Drop audio here, or <span style={{ color: "#6366F1" }}>browse</span>
            </p>
            <p className="text-[11px] mt-0.5" style={{ color: "#CBD5E1" }}>MP3 or WAV · max 200 MB</p>
          </div>
          <input ref={inputRef} type="file" accept=".mp3,.wav,audio/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
        </div>
      ) : (
        <div className="rounded-xl p-4" style={{
          background: isDone ? "#F0FDF4" : isError ? "#FEF2F2" : "#F8FAFC",
          border: `1px solid ${isDone ? "#BBF7D0" : isError ? "#FECACA" : "#E2E8F0"}`,
        }}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <FileAudio size={15} style={{ color: isDone ? "#16A34A" : isError ? "#DC2626" : "#6366F1" }} />
              <span className="text-[13px] font-medium truncate max-w-[200px]" style={{ color: "#0F172A" }}>{fileName}</span>
            </div>
            {isDone
              ? <CheckCircle size={16} style={{ color: "#22C55E" }} />
              : <button onClick={reset} className="p-1 rounded hover:bg-slate-200"><X size={13} style={{ color: "#94A3B8" }} /></button>}
          </div>

          {!isError && (
            <>
              <div className="h-2 rounded-full overflow-hidden mb-2" style={{ background: "#E2E8F0" }}>
                <div className="h-full rounded-full transition-all duration-300"
                  style={{ width: `${progress}%`, background: isDone ? "#22C55E" : "linear-gradient(90deg, #6366F1, #818CF8)" }} />
              </div>
              <div className="flex items-center justify-between">
                <p className="text-[12px] font-medium" style={{ color: isDone ? "#16A34A" : "#6366F1" }}>
                  {STAGE_LABELS[stage]}
                </p>
                <span className="font-mono text-[12px] font-semibold" style={{ color: isDone ? "#16A34A" : "#6366F1" }}>
                  {Math.round(progress)}%
                </span>
              </div>
            </>
          )}

          {isError && (
            <p className="text-[12px]" style={{ color: "#DC2626" }}>{errorMsg}</p>
          )}

          {isDone && (
            <button onClick={() => navigate(`/calls/${callId}`)}
              className="mt-3 w-full py-2 rounded-lg text-[13px] font-semibold"
              style={{ background: "#22C55E", color: "white" }}>
              View Analysis →
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

type AttentionReason = "unresolved" | "high_risk" | "high_attention";

function getReasons(call: CallSummary): AttentionReason[] {
  const reasons: AttentionReason[] = [];
  if (call.resolved === false) reasons.push("unresolved");
  if (call.risk_level === "HIGH" || call.risk_level === "CRITICAL") reasons.push("high_risk");
  if ((call.attention_score ?? 0) >= 70) reasons.push("high_attention");
  return reasons;
}

const REASON_LABELS: Record<AttentionReason, string> = {
  unresolved: "Unresolved",
  high_risk: "High Risk",
  high_attention: "High Attention",
};
const REASON_STYLE: Record<AttentionReason, { bg: string; color: string; border: string }> = {
  unresolved:     { bg: "#FEF3C7", color: "#D97706", border: "#FDE68A" },
  high_risk:      { bg: "#FEE2E2", color: "#DC2626", border: "#FECACA" },
  high_attention: { bg: "#EEF2FF", color: "#6366F1", border: "#C7D2FE" },
};

const RISK_ORDER: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

function RiskChip({ level }: { level: string | null }) {
  if (!level) return <span style={{ color: "#CBD5E1" }}>—</span>;
  const colors: Record<string, { bg: string; color: string }> = {
    CRITICAL: { bg: "#FEE2E2", color: "#DC2626" },
    HIGH:     { bg: "#FEF3C7", color: "#D97706" },
    MEDIUM:   { bg: "#FEF9C3", color: "#CA8A04" },
    LOW:      { bg: "#DCFCE7", color: "#16A34A" },
  };
  const c = colors[level] ?? { bg: "#F1F5F9", color: "#64748B" };
  return (
    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
      style={{ background: c.bg, color: c.color }}>
      {level}
    </span>
  );
}

const ATTENTION_PAGE_SIZE = 10;
const UNRESOLVED_PAGE_SIZE = 5;

// ── Page ────────────────────────────────────────────────────────────────────────

export default function Overview() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [unresolvedCalls, setUnresolvedCalls] = useState<CallSummary[] | null>(null);
  const [attentionPage, setAttentionPage] = useState(1);
  const [unresolvedPage, setUnresolvedPage] = useState(1);
  const [intents, setIntents] = useState<TrendingIntent[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);

  useEffect(() => {
    api.calls.stats().then(setStats).catch(console.error);
    // Fetch all unresolved calls in one shot (typically small — ~75 out of 1441)
    api.calls.list({ page: 1, page_size: 200, outcome: "UNRESOLVED" })
      .then(res => setUnresolvedCalls(res.items))
      .catch(console.error);
    api.calls.trendingIntents(8).then(setIntents).catch(console.error);
    api.agents.list().then(a => setAgents(a.slice(0, 4))).catch(console.error);
  }, []);

  // Manager attention: unresolved + HIGH or CRITICAL risk only
  const managerCalls = useMemo(() => {
    if (!unresolvedCalls) return null;
    return unresolvedCalls
      .filter(c => c.risk_level === "HIGH" || c.risk_level === "CRITICAL")
      .sort((a, b) => {
        const aRisk = RISK_ORDER[a.risk_level ?? ""] ?? 0;
        const bRisk = RISK_ORDER[b.risk_level ?? ""] ?? 0;
        if (bRisk !== aRisk) return bRisk - aRisk;
        return (b.attention_score ?? 0) - (a.attention_score ?? 0);
      });
  }, [unresolvedCalls]);

  // Other unresolved: not HIGH/CRITICAL risk
  const otherUnresolved = useMemo(() => {
    if (!unresolvedCalls) return null;
    return unresolvedCalls
      .filter(c => c.risk_level !== "HIGH" && c.risk_level !== "CRITICAL")
      .sort((a, b) => (b.attention_score ?? 0) - (a.attention_score ?? 0));
  }, [unresolvedCalls]);

  const totalAttentionPages = managerCalls ? Math.max(1, Math.ceil(managerCalls.length / ATTENTION_PAGE_SIZE)) : 1;
  const pagedCalls = managerCalls
    ? managerCalls.slice((attentionPage - 1) * ATTENTION_PAGE_SIZE, attentionPage * ATTENTION_PAGE_SIZE)
    : [];

  const totalUnresolvedPages = otherUnresolved ? Math.max(1, Math.ceil(otherUnresolved.length / UNRESOLVED_PAGE_SIZE)) : 1;
  const pagedOtherUnresolved = otherUnresolved
    ? otherUnresolved.slice((unresolvedPage - 1) * UNRESOLVED_PAGE_SIZE, unresolvedPage * UNRESOLVED_PAGE_SIZE)
    : [];

  // KPI computations
  const needsAttention = stats
    ? ((stats.risk_breakdown?.HIGH ?? 0) + (stats.risk_breakdown?.CRITICAL ?? 0))
    : 0;
  const avgScore = stats?.avg_attention_score ?? 0;
  const scoreColor = avgScore >= 80 ? "#EF4444" : avgScore >= 60 ? "#F59E0B" : avgScore >= 40 ? "#CA8A04" : "#22C55E";
  const scoreBg = avgScore >= 80 ? "#FEF2F2" : avgScore >= 60 ? "#FEF3C7" : avgScore >= 40 ? "#FEFCE8" : "#F0FDF4";
  const scoreLabel = avgScore >= 80 ? "HIGH RISK" : avgScore >= 60 ? "MED RISK" : avgScore >= 40 ? "MOD RISK" : "LOW RISK";
  const scoreLabelBg = avgScore >= 80 ? "#FEE2E2" : avgScore >= 60 ? "#FEF3C7" : avgScore >= 40 ? "#FEFCE8" : "#DCFCE7";
  const scoreLabelColor = avgScore >= 80 ? "#DC2626" : avgScore >= 60 ? "#D97706" : avgScore >= 40 ? "#CA8A04" : "#16A34A";
  const unresolvedPct = stats && stats.done_calls
    ? Math.round((stats.unresolved_count / stats.done_calls) * 100)
    : 0;

  return (
    <div className="p-6 space-y-5">
      {/* ── KPIs + Upload ── */}
      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr 300px" }}>
        <div className="card p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: "#94A3B8" }}>Total Processed</p>
          <div className="flex items-end justify-between">
            <span className="text-[40px] font-bold leading-none tabular-nums" style={{ color: "#0F172A" }}>
              {stats?.done_calls.toLocaleString() ?? "—"}
            </span>
            <div className="flex flex-col items-end gap-1">
              <span className="flex items-center gap-0.5 text-[12px] font-semibold" style={{ color: "#22C55E" }}>
                <ArrowUpRight size={13} /> {stats ? `${stats.done_calls} done` : ""}
              </span>
            </div>
          </div>
          <p className="text-[12px] mt-2" style={{ color: "#94A3B8" }}>
            {stats ? `${stats.pending_calls} pending · ${stats.failed_calls} failed` : "Loading…"}
          </p>
        </div>

        <div className="card p-5" style={{ borderColor: "#FDE68A", background: "#FFFBEB" }}>
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: "#94A3B8" }}>High Risk Calls</p>
          <div className="flex items-end justify-between">
            <span className="text-[40px] font-bold leading-none tabular-nums" style={{ color: "#F59E0B" }}>
              {stats ? needsAttention : "—"}
            </span>
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: "#FEF3C7" }}>
              <AlertTriangle size={18} style={{ color: "#F59E0B" }} />
            </div>
          </div>
          <p className="text-[12px] mt-2" style={{ color: "#94A3B8" }}>
            {stats ? `${stats.escalated_count} escalated` : "Loading…"}
          </p>
        </div>

        <div className="card p-5" style={{ borderColor: "#FECACA", background: "#FEF2F2" }}>
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: "#94A3B8" }}>Unresolved</p>
          <div className="flex items-end justify-between">
            <span className="text-[40px] font-bold leading-none tabular-nums" style={{ color: "#EF4444" }}>
              {stats?.unresolved_count ?? "—"}
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-md font-semibold"
              style={{ background: "#FEE2E2", color: "#EF4444" }}>{unresolvedPct}%</span>
          </div>
          <p className="text-[12px] mt-2" style={{ color: "#94A3B8" }}>
            {stats?.resolved_count.toLocaleString()} resolved
          </p>
        </div>

        <div className="card p-5" style={{ background: scoreBg }}>
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-4" style={{ color: "#94A3B8" }}>Avg Attention Score</p>
          <div className="flex items-end justify-between mb-3">
            <span className="text-[40px] font-bold leading-none tabular-nums" style={{ color: scoreColor }}>
              {avgScore ? Math.round(avgScore) : "—"}
            </span>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md"
              style={{ background: scoreLabelBg, color: scoreLabelColor }}>{scoreLabel}</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden mb-1" style={{ background: "#F1F5F9" }}>
            <div className="h-full rounded-full"
              style={{ width: `${Math.round(avgScore)}%`, background: `linear-gradient(90deg, #22C55E, ${scoreColor})` }} />
          </div>
          <div className="flex justify-between text-[10px]" style={{ color: "#CBD5E1" }}>
            <span>0</span><span>{Math.round(avgScore)} / 100</span><span>100</span>
          </div>
        </div>

        <UploadWidget />
      </div>

      {/* ── Requires Manager Attention ── */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid #F1F5F9" }}>
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ background: "#FEF2F2" }}>
              <ShieldAlert size={14} style={{ color: "#EF4444" }} />
            </div>
            <h2 className="font-semibold text-[15px]" style={{ color: "#0F172A" }}>Requires Manager Attention</h2>
            {managerCalls !== null && (
              <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
                style={{ background: managerCalls.length > 0 ? "#FEE2E2" : "#DCFCE7", color: managerCalls.length > 0 ? "#DC2626" : "#16A34A", border: `1px solid ${managerCalls.length > 0 ? "#FECACA" : "#BBF7D0"}` }}>
                {managerCalls.length} {managerCalls.length === 1 ? "call" : "calls"}
              </span>
            )}
          </div>
          {totalAttentionPages > 1 && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setAttentionPage(p => Math.max(1, p - 1))}
                disabled={attentionPage === 1}
                className="w-7 h-7 rounded-md flex items-center justify-center transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                <ChevronLeft size={13} />
              </button>
              <span className="text-[12px] px-2" style={{ color: "#94A3B8" }}>
                {attentionPage} / {totalAttentionPages}
              </span>
              <button
                onClick={() => setAttentionPage(p => Math.min(totalAttentionPages, p + 1))}
                disabled={attentionPage === totalAttentionPages}
                className="w-7 h-7 rounded-md flex items-center justify-center transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                <ChevronRight size={13} />
              </button>
            </div>
          )}
        </div>

        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid #F1F5F9", background: "#FAFBFC" }}>
              {["Customer", "Agent", "Risk", "Attention Score", "Flagged For", "Duration", "Time", "Action"].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#94A3B8" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {managerCalls === null ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-[13px]" style={{ color: "#94A3B8" }}>
                  Loading…
                </td>
              </tr>
            ) : managerCalls.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <div className="w-10 h-10 rounded-full flex items-center justify-center"
                      style={{ background: "#F0FDF4" }}>
                      <ShieldAlert size={18} style={{ color: "#22C55E" }} />
                    </div>
                    <p className="text-[14px] font-medium" style={{ color: "#22C55E" }}>No calls require manager attention</p>
                    <p className="text-[12px]" style={{ color: "#94A3B8" }}>All high-risk and unresolved calls have been handled.</p>
                  </div>
                </td>
              </tr>
            ) : (
              pagedCalls.map((call, i) => {
                const reasons = getReasons(call);
                const rowBg = i % 2 === 0 ? "transparent" : "#FAFBFC";
                return (
                  <tr key={call.call_id}
                    onClick={() => navigate(`/calls/${call.call_id}`)}
                    className="cursor-pointer group"
                    style={{ borderBottom: "1px solid #F8FAFC", background: rowBg }}
                    onMouseEnter={e => (e.currentTarget.style.background = "#FFF7F0")}
                    onMouseLeave={e => (e.currentTarget.style.background = rowBg)}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                          style={{ background: "linear-gradient(135deg,#6366F1,#4F46E5)", color: "white" }}>
                          {initials(call.customer_name)}
                        </div>
                        <span className="text-[13px] font-medium" style={{ color: "#0F172A" }}>{call.customer_name ?? "—"}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[13px]" style={{ color: "#64748B" }}>{call.agent_name ?? "—"}</td>
                    <td className="px-4 py-3"><RiskChip level={call.risk_level} /></td>
                    <td className="px-4 py-3"><ScoreBadge score={call.attention_score ?? 0} /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1 flex-wrap">
                        {reasons.map(r => (
                          <span key={r} className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
                            style={{ background: REASON_STYLE[r].bg, color: REASON_STYLE[r].color, border: `1px solid ${REASON_STYLE[r].border}` }}>
                            {REASON_LABELS[r]}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>{fmtDuration(call.duration_seconds)}</td>
                    <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>
                      {fmtTime(call.call_start_utc ?? call.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        className="text-[12px] font-medium px-3 py-1 rounded-md opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ background: "rgba(239,68,68,0.08)", color: "#EF4444", border: "1px solid rgba(239,68,68,0.2)" }}
                        onClick={e => { e.stopPropagation(); navigate(`/calls/${call.call_id}`); }}>
                        Review →
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Pagination footer */}
        {managerCalls && managerCalls.length > 0 && totalAttentionPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3" style={{ borderTop: "1px solid #F1F5F9" }}>
            <p className="text-[12px]" style={{ color: "#94A3B8" }}>
              Showing {((attentionPage - 1) * ATTENTION_PAGE_SIZE) + 1}–{Math.min(attentionPage * ATTENTION_PAGE_SIZE, managerCalls.length)} of {managerCalls.length}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setAttentionPage(p => Math.max(1, p - 1))}
                disabled={attentionPage === 1}
                className="flex items-center gap-1 text-[12px] font-medium px-2.5 py-1.5 rounded-md transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                <ChevronLeft size={12} /> Prev
              </button>
              {Array.from({ length: totalAttentionPages }, (_, i) => i + 1)
                .filter(p => p === 1 || p === totalAttentionPages || Math.abs(p - attentionPage) <= 1)
                .reduce<(number | "…")[]>((acc, p, idx, arr) => {
                  if (idx > 0 && (p as number) - (arr[idx - 1] as number) > 1) acc.push("…");
                  acc.push(p);
                  return acc;
                }, [])
                .map((p, idx) =>
                  p === "…"
                    ? <span key={`ellipsis-${idx}`} className="text-[12px] px-1" style={{ color: "#CBD5E1" }}>…</span>
                    : (
                      <button key={p}
                        onClick={() => setAttentionPage(p as number)}
                        className="w-7 h-7 rounded-md text-[12px] font-medium transition-all"
                        style={{
                          background: attentionPage === p ? "#6366F1" : "transparent",
                          color: attentionPage === p ? "white" : "#64748B",
                          border: attentionPage === p ? "none" : "1px solid #E2E8F0",
                        }}>
                        {p}
                      </button>
                    )
                )}
              <button
                onClick={() => setAttentionPage(p => Math.min(totalAttentionPages, p + 1))}
                disabled={attentionPage === totalAttentionPages}
                className="flex items-center gap-1 text-[12px] font-medium px-2.5 py-1.5 rounded-md transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                Next <ChevronRight size={12} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Other Unresolved Calls ── */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid #F1F5F9" }}>
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ background: "#FEF3C7" }}>
              <AlertTriangle size={14} style={{ color: "#D97706" }} />
            </div>
            <h2 className="font-semibold text-[15px]" style={{ color: "#0F172A" }}>Unresolved Calls</h2>
            {otherUnresolved !== null && (
              <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
                style={{ background: otherUnresolved.length > 0 ? "#FEF3C7" : "#DCFCE7", color: otherUnresolved.length > 0 ? "#D97706" : "#16A34A", border: `1px solid ${otherUnresolved.length > 0 ? "#FDE68A" : "#BBF7D0"}` }}>
                {otherUnresolved.length} {otherUnresolved.length === 1 ? "call" : "calls"}
              </span>
            )}
          </div>
          {totalUnresolvedPages > 1 && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setUnresolvedPage(p => Math.max(1, p - 1))}
                disabled={unresolvedPage === 1}
                className="flex items-center gap-1 text-[12px] font-medium px-2.5 py-1.5 rounded-md transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                <ChevronLeft size={12} /> Prev
              </button>
              <span className="text-[12px] px-2" style={{ color: "#94A3B8" }}>
                {unresolvedPage} / {totalUnresolvedPages}
              </span>
              <button
                onClick={() => setUnresolvedPage(p => Math.min(totalUnresolvedPages, p + 1))}
                disabled={unresolvedPage === totalUnresolvedPages}
                className="flex items-center gap-1 text-[12px] font-medium px-2.5 py-1.5 rounded-md transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                Next <ChevronRight size={12} />
              </button>
            </div>
          )}
        </div>

        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid #F1F5F9", background: "#FAFBFC" }}>
              {["Customer", "Agent", "Risk", "Score", "Top Moment", "Duration", "Time", ""].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#94A3B8" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {otherUnresolved === null ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-[13px]" style={{ color: "#94A3B8" }}>Loading…</td>
              </tr>
            ) : otherUnresolved.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center">
                  <p className="text-[14px] font-medium" style={{ color: "#22C55E" }}>No unresolved calls</p>
                </td>
              </tr>
            ) : (
              pagedOtherUnresolved.map((call, i) => {
                const rowBg = i % 2 === 0 ? "transparent" : "#FAFBFC";
                return (
                  <tr key={call.call_id}
                    onClick={() => navigate(`/calls/${call.call_id}`)}
                    className="cursor-pointer group"
                    style={{ borderBottom: "1px solid #F8FAFC", background: rowBg }}
                    onMouseEnter={e => (e.currentTarget.style.background = "#FFFBEB")}
                    onMouseLeave={e => (e.currentTarget.style.background = rowBg)}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                          style={{ background: "linear-gradient(135deg,#F59E0B,#D97706)", color: "white" }}>
                          {initials(call.customer_name)}
                        </div>
                        <span className="text-[13px] font-medium" style={{ color: "#0F172A" }}>{call.customer_name ?? "—"}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[13px]" style={{ color: "#64748B" }}>{call.agent_name ?? "—"}</td>
                    <td className="px-4 py-3"><RiskChip level={call.risk_level} /></td>
                    <td className="px-4 py-3"><ScoreBadge score={call.attention_score ?? 0} /></td>
                    <td className="px-4 py-3">{call.top_moment_type && <MomentBadge type={call.top_moment_type} small />}</td>
                    <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>{fmtDuration(call.duration_seconds)}</td>
                    <td className="px-4 py-3 font-mono text-[12px]" style={{ color: "#94A3B8" }}>
                      {fmtTime(call.call_start_utc ?? call.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        className="text-[12px] font-medium px-3 py-1 rounded-md opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ background: "rgba(245,158,11,0.1)", color: "#D97706", border: "1px solid rgba(245,158,11,0.25)" }}
                        onClick={e => { e.stopPropagation(); navigate(`/calls/${call.call_id}`); }}>
                        Review →
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {otherUnresolved && otherUnresolved.length > 0 && (
          <div className="flex items-center justify-between px-5 py-3" style={{ borderTop: "1px solid #F1F5F9" }}>
            <p className="text-[12px]" style={{ color: "#94A3B8" }}>
              Showing {((unresolvedPage - 1) * UNRESOLVED_PAGE_SIZE) + 1}–{Math.min(unresolvedPage * UNRESOLVED_PAGE_SIZE, otherUnresolved.length)} of {otherUnresolved.length}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setUnresolvedPage(p => Math.max(1, p - 1))}
                disabled={unresolvedPage === 1}
                className="flex items-center gap-1 text-[12px] font-medium px-2.5 py-1.5 rounded-md transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                <ChevronLeft size={12} /> Prev
              </button>
              <button
                onClick={() => setUnresolvedPage(p => Math.min(totalUnresolvedPages, p + 1))}
                disabled={unresolvedPage === totalUnresolvedPages}
                className="flex items-center gap-1 text-[12px] font-medium px-2.5 py-1.5 rounded-md transition-all disabled:opacity-30"
                style={{ border: "1px solid #E2E8F0", color: "#64748B" }}>
                Next <ChevronRight size={12} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Trending Intents + Agent Performance ── */}
      <div className="grid gap-4" style={{ gridTemplateColumns: "3fr 2fr" }}>
        <div className="card p-5">
          <h2 className="font-semibold text-[15px] mb-5" style={{ color: "#0F172A" }}>Trending Call Intents</h2>
          {intents.length === 0 ? (
            <p className="text-[13px]" style={{ color: "#94A3B8" }}>Loading…</p>
          ) : (
            <div className="space-y-3">
              {intents.map((intent, i) => {
                const max = intents[0].count;
                const pct = (intent.count / max) * 100;
                return (
                  <div key={intent.intent} className="flex items-center gap-3">
                    <span className="text-[12px] w-[160px] flex-shrink-0 truncate" style={{ color: "#64748B" }}
                      title={intent.intent}>{intent.intent || "—"}</span>
                    <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: "#F1F5F9" }}>
                      <div className="h-full rounded-full"
                        style={{ width: `${pct}%`, background: i < 3 ? "#6366F1" : "#818CF8" }} />
                    </div>
                    <div className="flex items-center gap-1.5 w-16 justify-end">
                      <span className="font-mono text-[12px] font-semibold" style={{ color: "#0F172A" }}>
                        {intent.count.toLocaleString()}
                      </span>
                      {i < 3
                        ? <TrendingUp size={11} style={{ color: "#EF4444" }} />
                        : <TrendingDown size={11} style={{ color: "#22C55E" }} />}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card p-5">
          <h2 className="font-semibold text-[15px] mb-4" style={{ color: "#0F172A" }}>Agent Performance</h2>
          <div className="text-[10px] font-semibold uppercase tracking-wider grid mb-3 px-2"
            style={{ color: "#94A3B8", gridTemplateColumns: "32px 1fr 44px 56px 48px" }}>
            <span /><span>Agent</span>
            <span className="text-right">Calls</span>
            <span className="text-right">Resolved</span>
            <span className="text-right">Score</span>
          </div>
          {agents.length === 0 ? (
            <p className="px-2 text-[13px]" style={{ color: "#94A3B8" }}>Loading…</p>
          ) : (
            <div className="space-y-1">
              {agents.map(agent => {
                const score = agent.avg_attention_score ?? 0;
                return (
                  <div key={agent.agent_name}
                    className="grid items-center px-2 py-2 rounded-lg cursor-pointer hover:bg-slate-50"
                    style={{ gridTemplateColumns: "32px 1fr 44px 56px 48px" }}
                    onClick={() => navigate(`/agents/${encodeURIComponent(agent.agent_name)}`)}>
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold"
                      style={{ background: "#EEF2FF", color: "#6366F1" }}>{initials(agent.agent_name)}</div>
                    <span className="text-[13px] pl-2 font-medium truncate" style={{ color: "#0F172A" }}>{agent.agent_name}</span>
                    <span className="font-mono text-[12px] text-right" style={{ color: "#94A3B8" }}>{agent.call_count}</span>
                    <span className="font-mono text-[12px] text-right font-semibold" style={{ color: "#22C55E" }}>
                      {Math.round(agent.call_count * agent.resolution_rate)} ✓
                    </span>
                    <span className="font-mono text-[12px] text-right font-bold"
                      style={{ color: score < 30 ? "#22C55E" : score < 50 ? "#F59E0B" : "#EF4444" }}>
                      {Math.round(score)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          <button onClick={() => navigate("/agents")}
            className="w-full mt-3 pt-3 text-[12px] font-medium flex items-center justify-center gap-1"
            style={{ borderTop: "1px solid #F1F5F9", color: "#6366F1" }}>
            View all agents <ChevronRight size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
