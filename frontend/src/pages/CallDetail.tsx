import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate, useParams } from "react-router";
import { Play, Pause, SkipBack, SkipForward, Volume2, Flag, Download, Search } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ReferenceArea, ResponsiveContainer,
} from "recharts";
import {
  api, type CallDetailResponse, type MomentItem, type TurnItem, type EvidenceItem,
} from "../lib/api";
import { fmtTime, fmtDuration, fmtMMSS } from "../lib/format";
import { MomentBadge, ScoreBadge, getMomentColor } from "../components/Badges";

type AttentionObj = { total: number; components: Array<{ label: string; points: number; moment_id: number }> };

// ─── helpers ──────────────────────────────────────────────────────────────────

const BARS = Array.from({ length: 200 }, (_, i) => {
  const a = Math.abs(Math.sin(i * 0.41) * 28);
  const b = Math.abs(Math.sin(i * 0.17 + 1.3) * 18);
  const c = Math.abs(Math.sin(i * 0.73 + 0.7) * 12);
  return Math.max(8, Math.min(95, a + b + c));
});

// ─── Audio Player ─────────────────────────────────────────────────────────────

function AudioPlayer({
  callId, currentTime, onSeek, totalSeconds, moments, activeMomentId, onMomentClick,
}: {
  callId: string; currentTime: number; onSeek: (t: number) => void;
  totalSeconds: number;
  moments: MomentItem[];
  activeMomentId: number | null;
  onMomentClick: (id: number) => void;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(80);
  const [speed, setSpeed] = useState("1x");
  const [audioAvailable, setAudioAvailable] = useState(true);
  const lastSeekRef = useRef(0);
  const total = totalSeconds || 1;
  const progress = (currentTime / total) * 100;
  const audioSrc = api.calls.audioUrl(callId);

  // Sync timeupdate → parent state
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onUpdate = () => {
      lastSeekRef.current = audio.currentTime;
      onSeek(audio.currentTime);
    };
    const onEnded = () => setPlaying(false);
    audio.addEventListener("timeupdate", onUpdate);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onUpdate);
      audio.removeEventListener("ended", onEnded);
    };
  }, [onSeek]);

  // Seek when parent drives currentTime from outside (transcript/moment click)
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || Math.abs(currentTime - lastSeekRef.current) < 0.5) return;
    audio.currentTime = currentTime;
    lastSeekRef.current = currentTime;
  }, [currentTime]);

  // Sync volume
  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume / 100;
  }, [volume]);

  // Sync playback rate
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = parseFloat(speed);
  }, [speed]);

  const handlePlayPause = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) { audio.pause(); setPlaying(false); }
    else { audio.play().catch(() => {}); setPlaying(true); }
  };

  const handleWaveformClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = ((e.clientX - rect.left) / rect.width) * total;
    if (audioRef.current) { audioRef.current.currentTime = t; lastSeekRef.current = t; }
    onSeek(t);
  };

  return (
    <div className="card p-4">
      {/* Hidden audio element */}
      <audio
        ref={audioRef}
        src={audioAvailable ? audioSrc : undefined}
        preload="metadata"
        onError={() => setAudioAvailable(false)}
      />

      <div
        className="relative rounded-xl overflow-visible cursor-pointer select-none mb-5"
        style={{ height: 72, background: "#F8FAFC", border: "1px solid #E8EDF5" }}
        onClick={handleWaveformClick}>
        <div className="absolute inset-0 flex items-center gap-px px-3 overflow-hidden rounded-xl">
          {BARS.map((h, i) => {
            const isPast = (i / BARS.length) * 100 <= progress;
            return (
              <div key={i} className="flex-1 rounded-full"
                style={{ height: `${h}%`, background: isPast ? "#6366F1" : "#DDE3EF", opacity: isPast ? 1 : 0.8 }} />
            );
          })}
        </div>
        <div className="absolute top-0 bottom-0 w-0.5 z-10 pointer-events-none"
          style={{ left: `${progress}%`, background: "#4F46E5", boxShadow: "0 0 6px rgba(99,102,241,0.5)" }} />
        {moments.map(m => {
          const pct = (m.start_time / total) * 100;
          const color = getMomentColor(m.moment_type);
          const isActive = activeMomentId === m.moment_id;
          return (
            <div key={m.moment_id} className="absolute group z-20"
              style={{ left: `${pct}%`, bottom: -12, transform: "translateX(-50%)" }}>
              <button
                className="w-4 h-4 rounded-full border-2"
                style={{ background: isActive ? color : "#FFFFFF", borderColor: color,
                  boxShadow: isActive ? `0 0 8px ${color}60` : `0 1px 3px rgba(0,0,0,0.12)` }}
                onClick={e => { e.stopPropagation(); onMomentClick(m.moment_id); onSeek(m.start_time); }} />
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-4 hidden group-hover:block pointer-events-none z-30 whitespace-nowrap">
                <div className="text-[10px] px-2.5 py-1.5 rounded-lg shadow-lg"
                  style={{ background: "#FFFFFF", border: `1px solid ${color}50`, color: "#0F172A", boxShadow: "0 4px 12px rgba(0,0,0,0.12)" }}>
                  <div className="font-semibold" style={{ color }}>{m.moment_type.replace(/_/g, " ")}</div>
                  <div style={{ color: "#94A3B8" }}>at {fmtMMSS(m.start_time)}</div>
                  {m.trigger_phrase && (
                    <div className="mt-0.5 italic max-w-[180px] truncate" style={{ color: "#64748B" }}>"{m.trigger_phrase}"</div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <button className="p-2 rounded-lg hover:bg-slate-100" style={{ color: "#94A3B8" }}
            onClick={() => { if (audioRef.current) { audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 10); } }}>
            <SkipBack size={14} />
          </button>
          <button
            className="w-9 h-9 rounded-full flex items-center justify-center"
            style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", boxShadow: "0 2px 8px rgba(99,102,241,0.35)" }}
            onClick={handlePlayPause}>
            {playing ? <Pause size={14} color="white" /> : <Play size={14} color="white" style={{ marginLeft: 1 }} />}
          </button>
          <button className="p-2 rounded-lg hover:bg-slate-100" style={{ color: "#94A3B8" }}
            onClick={() => { if (audioRef.current) { audioRef.current.currentTime = Math.min(total, audioRef.current.currentTime + 10); } }}>
            <SkipForward size={14} />
          </button>
        </div>
        <span className="font-mono text-[12px] tabular-nums" style={{ color: "#64748B" }}>
          <span style={{ color: "#0F172A", fontWeight: 600 }}>{fmtMMSS(currentTime)}</span>
          <span> / {fmtMMSS(total)}</span>
        </span>
        {!audioAvailable && (
          <span className="text-[11px]" style={{ color: "#94A3B8" }}>audio file not found</span>
        )}
        <div className="flex items-center gap-2 ml-auto">
          <Volume2 size={12} style={{ color: "#CBD5E1" }} />
          <input type="range" min={0} max={100} value={volume} onChange={e => setVolume(+e.target.value)}
            className="w-16 cursor-pointer" style={{ accentColor: "#6366F1" }} />
        </div>
        <div className="flex gap-0.5 p-0.5 rounded-lg" style={{ background: "#F1F5F9" }}>
          {["0.75x", "1x", "1.25x", "1.5x", "2x"].map(s => (
            <button key={s} onClick={() => setSpeed(s)}
              className="text-[11px] px-2 py-1 rounded-md font-mono"
              style={{ background: speed === s ? "#6366F1" : "transparent", color: speed === s ? "white" : "#94A3B8" }}>
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Mood Chart ───────────────────────────────────────────────────────────────

interface MoodPoint { time: number; score: number; label: string; }

function MoodChart({ data, onSeek }: { data: MoodPoint[]; onSeek: (t: number) => void }) {
  if (!data.length) return null;

  const CustomDot = (props: any) => {
    const { cx, cy, payload } = props;
    const color = payload.score > 0.3 ? "#22C55E" : payload.score > -0.3 ? "#F59E0B" : "#EF4444";
    return <circle cx={cx} cy={cy} r={5} fill={color} stroke="#FFFFFF" strokeWidth={2}
      style={{ cursor: "pointer" }} onClick={() => onSeek(payload.time * 60)} />;
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.[0]) return null;
    const d = payload[0].payload;
    const color = d.score > 0.3 ? "#22C55E" : d.score > -0.3 ? "#F59E0B" : "#EF4444";
    return (
      <div className="px-3 py-2 rounded-lg text-[12px]"
        style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}>
        <p className="font-mono mb-1" style={{ color: "#94A3B8" }}>{fmtMMSS(d.time * 60)}</p>
        {d.label && <p className="mb-1" style={{ color: "#64748B" }}>{d.label}</p>}
        <p className="font-mono font-bold" style={{ color }}>{d.score > 0 ? "+" : ""}{d.score.toFixed(2)}</p>
      </div>
    );
  };

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-semibold text-[14px]" style={{ color: "#0F172A" }}>Customer Mood Timeline</h3>
        <div className="flex items-center gap-3 text-[11px]" style={{ color: "#94A3B8" }}>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: "#22C55E" }} />Positive</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: "#F59E0B" }} />Neutral</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: "#EF4444" }} />Negative</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="moodLine" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#22C55E" /><stop offset="50%" stopColor="#F59E0B" /><stop offset="100%" stopColor="#EF4444" />
            </linearGradient>
          </defs>
          <ReferenceArea y1={0.3} y2={1} fill="#22C55E" fillOpacity={0.04} />
          <ReferenceArea y1={-0.3} y2={0.3} fill="#F59E0B" fillOpacity={0.04} />
          <ReferenceArea y1={-1} y2={-0.3} fill="#EF4444" fillOpacity={0.05} />
          <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
          <XAxis dataKey="time" tickFormatter={v => fmtMMSS(v * 60)}
            tick={{ fill: "#CBD5E1", fontSize: 10 }} axisLine={{ stroke: "#E2E8F0" }} tickLine={false} />
          <YAxis domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]}
            tickFormatter={v => v === 1 ? "+1" : v === 0 ? "0" : v === -1 ? "−1" : ""}
            tick={{ fill: "#CBD5E1", fontSize: 10 }} axisLine={{ stroke: "#E2E8F0" }} tickLine={false} />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={0} stroke="#E2E8F0" strokeWidth={1} />
          <Line type="monotone" dataKey="score" stroke="url(#moodLine)" strokeWidth={2.5}
            dot={<CustomDot />} activeDot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Moments Panel ────────────────────────────────────────────────────────────

function MomentsPanel({
  moments, totalSeconds, activeMomentId, onMomentClick,
}: {
  moments: MomentItem[]; totalSeconds: number;
  activeMomentId: number | null; onMomentClick: (id: number) => void;
}) {
  const total = totalSeconds || 1;
  return (
    <div className="card p-5">
      <h3 className="font-semibold text-[14px] mb-3" style={{ color: "#0F172A" }}>Detected Moments</h3>

      <div className="relative h-1 mb-6 rounded-full" style={{ background: "#F1F5F9" }}>
        {moments.map(m => {
          const pct = (m.start_time / total) * 100;
          const color = getMomentColor(m.moment_type);
          const isActive = activeMomentId === m.moment_id;
          return (
            <button key={m.moment_id} className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2"
              style={{ left: `${pct}%` }} onClick={() => onMomentClick(m.moment_id)}>
              <div className="rounded-full"
                style={{
                  width: isActive ? 14 : 10, height: isActive ? 14 : 10, background: color,
                  boxShadow: isActive ? `0 0 0 3px ${color}25, 0 0 8px ${color}50` : `0 1px 3px rgba(0,0,0,0.12)`,
                }} />
            </button>
          );
        })}
      </div>

      <div className="space-y-2.5">
        {moments.map(m => {
          const color = getMomentColor(m.moment_type);
          const isActive = activeMomentId === m.moment_id;
          const conf = Math.round((m.confidence ?? 0) * 100);
          return (
            <div key={m.moment_id} className="rounded-xl p-4 cursor-pointer hover:shadow-sm"
              style={{
                background: isActive ? `${color}08` : "#FAFBFC",
                border: `1px solid ${isActive ? color + "35" : "#E2E8F0"}`,
              }}
              onClick={() => onMomentClick(m.moment_id)}>
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2">
                  <MomentBadge type={m.moment_type} />
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
                    style={{ background: "#F1F5F9", color: "#94A3B8" }}>{m.severity}</span>
                </div>
                <span className="font-mono text-[11px] px-2 py-0.5 rounded-md"
                  style={{ background: "rgba(99,102,241,0.08)", color: "#6366F1", border: "1px solid rgba(99,102,241,0.2)" }}>
                  ▶ {fmtMMSS(m.start_time)}
                </span>
              </div>
              {m.trigger_phrase && (
                <div className="rounded-lg px-3 py-2 mb-2.5"
                  style={{ background: "#FFFFFF", borderLeft: `2px solid ${color}`, border: "1px solid #E2E8F0", borderLeftWidth: 2 }}>
                  <p className="text-[12px] font-mono italic leading-relaxed" style={{ color: "#64748B" }}>
                    "{m.trigger_phrase}"
                  </p>
                </div>
              )}
              {m.description && (
                <p className="text-[12px] mb-2" style={{ color: "#64748B" }}>{m.description}</p>
              )}
              {m.confidence != null && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px]" style={{ color: "#94A3B8" }}>Confidence</span>
                  <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: "#F1F5F9" }}>
                    <div className="h-full rounded-full" style={{ width: `${conf}%`, background: color }} />
                  </div>
                  <span className="text-[11px] font-mono font-semibold" style={{ color }}>{conf}%</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Transcript Panel ─────────────────────────────────────────────────────────

function TranscriptPanel({
  turns, moments, activeMomentId, highlightTurnId, onTurnClick,
}: {
  turns: TurnItem[]; moments: MomentItem[];
  activeMomentId: number | null; highlightTurnId: number | null;
  onTurnClick: (t: number) => void;
}) {
  const [search, setSearch] = useState("");
  const turnRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    if (highlightTurnId == null) return;
    turnRefs.current[highlightTurnId]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightTurnId]);

  const momentById = Object.fromEntries(moments.map(m => [m.moment_id, m]));

  return (
    <div className="card flex flex-col" style={{ height: 560 }}>
      <div className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid #F1F5F9" }}>
        <h3 className="font-semibold text-[14px]" style={{ color: "#0F172A" }}>Transcript</h3>
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "#CBD5E1" }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…"
            className="pl-7 pr-3 py-1.5 text-[12px] rounded-lg w-40 outline-none"
            style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", color: "#0F172A" }} />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {turns
          .filter(t => !search || t.text.toLowerCase().includes(search.toLowerCase()))
          .map(turn => {
            const isAgent = turn.speaker === "AGENT" || turn.speaker.toUpperCase().includes("AGENT");
            const activeMomentOnTurn = turn.moment_ids.includes(activeMomentId ?? -1)
              ? momentById[activeMomentId!] : null;
            const anyMoment = turn.moment_ids.length > 0 ? momentById[turn.moment_ids[0]] : null;
            const evidenceMoment = activeMomentOnTurn ?? anyMoment;
            const isHighlighted = turn.id === highlightTurnId;
            const color = evidenceMoment ? getMomentColor(evidenceMoment.moment_type) : null;

            return (
              <div key={turn.id} ref={el => { turnRefs.current[turn.id] = el; }}
                className={`flex ${isAgent ? "justify-start" : "justify-end"}`}>
                <div
                  className="max-w-[88%] rounded-xl p-3 cursor-pointer hover:shadow-sm"
                  style={{
                    background: isHighlighted && color ? `${color}08`
                      : evidenceMoment ? `${color}06` : isAgent ? "#F8FAFC" : "#EEF2FF",
                    border: `1px solid ${isHighlighted && color ? `${color}40`
                      : evidenceMoment ? `${color}25` : "#E2E8F0"}`,
                    borderLeft: `3px solid ${isHighlighted && color ? color
                      : evidenceMoment ? color : isAgent ? "#E2E8F0" : "#C7D2FE"}`,
                  }}
                  onClick={() => onTurnClick(turn.start_time)}>
                  <div className="flex items-center justify-between mb-1.5 gap-6">
                    <span className="text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: isAgent ? "#6366F1" : "#94A3B8" }}>{turn.speaker}</span>
                    <span className="font-mono text-[10px]" style={{ color: "#CBD5E1" }}>{fmtMMSS(turn.start_time)}</span>
                  </div>
                  <p className="text-[13px] leading-relaxed" style={{ color: "#0F172A" }}>{turn.text}</p>
                  {evidenceMoment && (
                    <div className="mt-2">
                      <span className="text-[10px] px-2 py-0.5 rounded-md font-medium"
                        style={{ background: `${color}12`, color: color ?? "#64748B" }}>
                        Evidence for: {evidenceMoment.moment_type.replace(/_/g, " ")}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}

// ─── Evidence Panel ───────────────────────────────────────────────────────────

function EvidencePanel({
  evidence, moments, onSeek, onHighlight,
}: {
  evidence: EvidenceItem[]; moments: MomentItem[];
  onSeek: (t: number) => void;
  onHighlight: (momentId: number, turnId: number) => void;
}) {
  const momentById = Object.fromEntries(moments.map(m => [m.moment_id, m]));
  return (
    <div className="card p-5">
      <h3 className="font-semibold text-[14px] mb-4" style={{ color: "#0F172A" }}>AI Judgments & Evidence</h3>
      <div className="space-y-3">
        {evidence.map((ev, idx) => {
          const isStrong = ev.strength === "STRONG";
          const conf = ev.confidence != null ? Math.round(ev.confidence * 100) : null;
          const linkedMoment = ev.moment_id != null ? momentById[ev.moment_id] : null;
          const typeLabel = linkedMoment ? linkedMoment.moment_type.replace(/_/g, " ") : `Evidence ${idx + 1}`;
          return (
            <div key={idx} className="rounded-xl p-4" style={{ background: "#FAFBFC", border: "1px solid #E2E8F0" }}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#94A3B8" }}>
                  {typeLabel}
                </span>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md"
                  style={{
                    background: isStrong ? "#DCFCE7" : "#FEF3C7",
                    color: isStrong ? "#16A34A" : "#D97706",
                    border: `1px solid ${isStrong ? "#BBF7D0" : "#FDE68A"}`,
                  }}>
                  {ev.strength}{conf != null ? ` · ${conf}%` : ""}
                </span>
              </div>
              {ev.claim && (
                <p className="text-[13px] mb-3 font-medium" style={{ color: "#0F172A" }}>{ev.claim}</p>
              )}
              <button
                className="w-full text-left rounded-lg p-3 hover:shadow-sm group"
                style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderLeft: "3px solid #6366F1" }}
                onClick={() => {
                  if (ev.timestamp != null) onSeek(ev.timestamp);
                  if (ev.moment_id != null) onHighlight(ev.moment_id, ev.turn_id);
                }}>
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-[11px]" style={{ color: "#94A3B8" }}>Turn #{ev.turn_id}</span>
                  {ev.timestamp != null && (
                    <span className="font-mono text-[11px]" style={{ color: "#6366F1" }}>
                      ▶ {fmtMMSS(ev.timestamp)}
                    </span>
                  )}
                </div>
                <p className="text-[12px] font-mono italic leading-relaxed" style={{ color: "#64748B" }}>
                  "{ev.quote}"
                </p>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Score Breakdown ──────────────────────────────────────────────────────────

function ScoreBreakdown({
  analysis, moments, onMomentClick,
}: {
  analysis: Record<string, unknown> | null;
  moments: MomentItem[];
  onMomentClick: (id: number) => void;
}) {
  // attention_score in the analysis blob is {total, components} — not a plain number
  const rawAttn = analysis?.attention_score as AttentionObj | number | undefined;
  const score = typeof rawAttn === "object" && rawAttn !== null ? (rawAttn.total ?? 0) : ((rawAttn as number) ?? 0);
  const blobComponents: AttentionObj["components"] = typeof rawAttn === "object" && rawAttn !== null ? (rawAttn.components ?? []) : [];

  const color = score >= 80 ? "#EF4444" : score >= 60 ? "#F59E0B" : score >= 40 ? "#CA8A04" : "#22C55E";
  const riskLabel = score >= 80 ? "HIGH RISK" : score >= 60 ? "MED RISK" : score >= 40 ? "MOD RISK" : "LOW RISK";
  const labelBg = score >= 80 ? "#FEE2E2" : score >= 60 ? "#FEF3C7" : score >= 40 ? "#FEFCE8" : "#DCFCE7";
  const labelColor = score >= 80 ? "#DC2626" : score >= 60 ? "#D97706" : score >= 40 ? "#CA8A04" : "#16A34A";

  // Prefer HIGH/CRITICAL moment factors; fall back to Claude's component reasoning
  const momentFactors: Array<{ label: string; points: number; color: string; momentId: number | null }> = moments
    .filter(m => m.severity === "HIGH" || m.severity === "CRITICAL")
    .slice(0, 5)
    .map(m => ({
      label: m.moment_type.replace(/_/g, " "),
      points: m.severity === "CRITICAL" ? 25 : 15,
      color: getMomentColor(m.moment_type),
      momentId: m.moment_id,
    }));
  const claudeFactors: Array<{ label: string; points: number; color: string; momentId: number | null }> =
    blobComponents.filter(c => c.label && c.label !== "claude assessment").map(c => ({
      label: c.label,
      points: c.points,
      color: "#6366F1",
      momentId: c.moment_id !== 0 ? c.moment_id : null,
    }));
  const factors = momentFactors.length > 0 ? momentFactors : claudeFactors;

  return (
    <div className="card p-5">
      <h3 className="font-semibold text-[14px] mb-4" style={{ color: "#0F172A" }}>Attention Score Breakdown</h3>
      <div className="flex items-end gap-4 mb-4">
        <span className="text-[56px] font-bold leading-none tabular-nums" style={{ color }}>{Math.round(score)}</span>
        <div className="pb-1">
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md inline-block mb-1"
            style={{ background: labelBg, color: labelColor, border: `1px solid ${labelColor}30` }}>
            {riskLabel}
          </span>
          <p className="text-[11px]" style={{ color: "#94A3B8" }}>capped at 100 · {moments.length} moments</p>
        </div>
      </div>
      <div className="h-1.5 rounded-full mb-5 overflow-hidden" style={{ background: "#F1F5F9" }}>
        <div className="h-full rounded-full"
          style={{ width: `${Math.round(score)}%`, background: "linear-gradient(90deg, #22C55E 0%, #F59E0B 40%, #EF4444 80%)" }} />
      </div>
      {factors.length > 0 && (
        <div className="space-y-2">
          {factors.map((item, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-slate-50 group">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 font-mono text-[12px] font-bold"
                style={{ background: `${item.color}12`, color: item.color, border: `1px solid ${item.color}25` }}>
                +{item.points}
              </div>
              <span className="flex-1 text-[12px] font-medium" style={{ color: "#475569" }}>{item.label}</span>
              {item.momentId != null && (
                <button
                  className="text-[11px] px-2.5 py-1 rounded-md opacity-0 group-hover:opacity-100 font-medium"
                  style={{ background: "rgba(99,102,241,0.1)", color: "#6366F1", border: "1px solid rgba(99,102,241,0.25)" }}
                  onClick={() => onMomentClick(item.momentId!)}>
                  View →
                </button>
              )}
            </div>
          ))}
          <div className="flex items-center gap-3 px-3 py-2" style={{ borderTop: "1px solid #F1F5F9", marginTop: 4 }}>
            <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 font-mono text-[13px] font-bold"
              style={{ background: labelBg, color: labelColor, border: `1px solid ${labelColor}30` }}>
              {Math.round(score)}
            </div>
            <span className="text-[12px] font-semibold" style={{ color: "#0F172A" }}>Total score (capped at 100)</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CallDetail() {
  const navigate = useNavigate();
  const { callId } = useParams<{ callId: string }>();
  const [detail, setDetail] = useState<CallDetailResponse | null>(null);
  const [turns, setTurns] = useState<TurnItem[]>([]);
  const [moments, setMoments] = useState<MomentItem[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [currentTime, setCurrentTime] = useState(0);
  const [activeMomentId, setActiveMomentId] = useState<number | null>(null);
  const [highlightTurnId, setHighlightTurnId] = useState<number | null>(null);

  useEffect(() => {
    if (!callId) return;
    setLoading(true);
    Promise.all([
      api.calls.detail(callId),
      api.calls.transcript(callId),
      api.calls.moments(callId),
      api.calls.evidence(callId),
    ]).then(([d, t, m, e]) => {
      setDetail(d);
      setTurns(t.turns);
      setMoments(m.moments);
      setEvidence(e.evidence);
    }).catch(console.error).finally(() => setLoading(false));
  }, [callId]);

  const handleSeek = useCallback((t: number) => setCurrentTime(t), []);

  const handleMomentActivate = useCallback((id: number) => {
    const m = moments.find(x => x.moment_id === id);
    if (!m) return;
    setCurrentTime(m.start_time);
    setActiveMomentId(id);
    const turn = turns.find(t => t.moment_ids.includes(id));
    if (turn) setHighlightTurnId(turn.id);
  }, [moments, turns]);

  const handleEvidenceHighlight = useCallback((momentId: number, turnId: number) => {
    setActiveMomentId(momentId);
    setHighlightTurnId(turnId);
  }, []);

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center py-24">
        <p className="text-[15px]" style={{ color: "#94A3B8" }}>Loading call…</p>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-6">
        <button onClick={() => navigate("/calls")} className="text-[13px] mb-4" style={{ color: "#6366F1" }}>← All Calls</button>
        <p style={{ color: "#EF4444" }}>Call not found.</p>
      </div>
    );
  }

  const analysis = detail.analysis ?? {};
  const totalSeconds = detail.duration_seconds ?? 0;
  const summaryText = (analysis.summary as string) ?? "";
  const moodRaw = (analysis.mood_trajectory as Array<Record<string, number | string>>) ?? [];
  const moodData: MoodPoint[] = moodRaw.map(p => ({
    time: (typeof p.timestamp === "number" ? p.timestamp : 0) / 60,
    score: typeof p.score === "number" ? p.score : 0,
    label: typeof p.label === "string" ? p.label : "",
  }));

  const score = detail.attention_score ?? 0;
  const scoreColor = score >= 80 ? "#EF4444" : score >= 60 ? "#F59E0B" : "#22C55E";
  const scoreLabel = score >= 80 ? "HIGH RISK" : score >= 60 ? "MED RISK" : "LOW RISK";

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button className="text-[12px] mb-2 flex items-center gap-1"
            style={{ color: "#94A3B8" }} onClick={() => navigate("/calls")}>
            ← All Calls
          </button>
          <h1 className="text-[24px] font-bold tracking-tight" style={{ color: "#0F172A" }}>
            Call <span style={{ color: "#6366F1" }}>#{callId?.slice(0, 8)}</span>
          </h1>
          <p className="text-[13px] mt-0.5" style={{ color: "#94A3B8" }}>
            {detail.customer_name ?? "Unknown customer"}
            <span style={{ color: "#CBD5E1" }}> → </span>
            {detail.agent_name ?? "Unknown agent"}
            <span style={{ color: "#CBD5E1" }}> · </span>
            {fmtTime(detail.call_start_utc ?? detail.created_at)}
            <span style={{ color: "#CBD5E1" }}> · </span>
            {fmtDuration(totalSeconds)}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl"
            style={{ background: score >= 80 ? "#FEF2F2" : score >= 60 ? "#FEF3C7" : "#F0FDF4",
              border: `1px solid ${scoreColor}30` }}>
            <span className="font-mono text-[28px] font-bold leading-none" style={{ color: scoreColor }}>{Math.round(score)}</span>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: scoreColor }}>{scoreLabel}</p>
              <p className="text-[10px]" style={{ color: "#94A3B8" }}>Attention Score</p>
            </div>
          </div>
          <span className="text-[12px] px-3 py-2 rounded-lg font-medium"
            style={{
              background: detail.resolved ? "#F0FDF4" : "#FEF2F2",
              color: detail.resolved ? "#16A34A" : "#EF4444",
              border: `1px solid ${detail.resolved ? "#BBF7D0" : "#FECACA"}`,
            }}>
            {detail.resolved ? "✅ Resolved" : "❌ Unresolved"}
          </span>
          <button className="flex items-center gap-1.5 text-[13px] px-3 py-2 rounded-lg"
            style={{ background: "#FEF3C7", color: "#D97706", border: "1px solid #FDE68A" }}>
            <Flag size={13} /> Flag for review
          </button>
          <button className="flex items-center gap-1.5 text-[13px] px-3 py-2 rounded-lg"
            style={{ background: "#FFFFFF", color: "#64748B", border: "1px solid #E2E8F0" }}>
            <Download size={13} /> Export
          </button>
        </div>
      </div>

      {/* Two-panel layout */}
      <div className="grid gap-5" style={{ gridTemplateColumns: "55fr 45fr" }}>
        {/* LEFT */}
        <div className="space-y-4 min-w-0">
          <AudioPlayer
            callId={callId!}
            currentTime={currentTime} onSeek={handleSeek}
            totalSeconds={totalSeconds} moments={moments}
            activeMomentId={activeMomentId} onMomentClick={handleMomentActivate} />

          {/* AI Summary */}
          {summaryText && (
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-5 h-5 rounded-md flex items-center justify-center"
                  style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}>
                  <span className="text-[10px] text-white">✦</span>
                </div>
                <h3 className="font-semibold text-[14px]" style={{ color: "#0F172A" }}>AI Summary</h3>
              </div>
              <p className="text-[14px] leading-relaxed" style={{ color: "#64748B" }}>{summaryText}</p>
              <div className="flex gap-2 mt-4 flex-wrap">
                {[
                  { label: "Intent", value: detail.intent ?? "—", color: "#6366F1", bg: "#EEF2FF" },
                  { label: "Outcome", value: detail.resolved ? "Resolved" : "Unresolved",
                    color: detail.resolved ? "#16A34A" : "#DC2626",
                    bg: detail.resolved ? "#F0FDF4" : "#FEF2F2" },
                  { label: "Risk", value: detail.risk_level ?? "—", color: "#D97706", bg: "#FEF3C7" },
                ].map(pill => (
                  <span key={pill.label} className="text-[12px] px-3 py-1.5 rounded-full flex items-center gap-1.5"
                    style={{ background: pill.bg, color: pill.color }}>
                    <span className="font-semibold">{pill.label}:</span>
                    <span style={{ opacity: 0.8 }}>{pill.value}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {moodData.length > 0 && <MoodChart data={moodData} onSeek={handleSeek} />}
          {moments.length > 0 && (
            <MomentsPanel moments={moments} totalSeconds={totalSeconds}
              activeMomentId={activeMomentId} onMomentClick={handleMomentActivate} />
          )}
        </div>

        {/* RIGHT */}
        <div className="space-y-4 min-w-0">
          <TranscriptPanel turns={turns} moments={moments}
            activeMomentId={activeMomentId} highlightTurnId={highlightTurnId}
            onTurnClick={handleSeek} />
          {evidence.length > 0 && (
            <EvidencePanel evidence={evidence} moments={moments}
              onSeek={handleSeek} onHighlight={handleEvidenceHighlight} />
          )}
          <ScoreBreakdown analysis={analysis} moments={moments} onMomentClick={handleMomentActivate} />
        </div>
      </div>
    </div>
  );
}
