type MomentType =
  | "ESCALATION_REQUEST" | "UNRESOLVED" | "FRAUD_SIGNAL" | "MANAGER_REQUEST"
  | "MOOD_SHIFT" | "REPEAT_CONTACT" | "COMPLAINT" | "LONG_SILENCE"
  | "OVERTALK" | "APOLOGY" | "RESOLUTION_ATTEMPT" | "COMPLIANCE_BREACH"
  | "POSITIVE_FEEDBACK" | "HOLD_PLACED";

const momentConfig: Record<MomentType, { bg: string; text: string; border: string; pulse?: boolean }> = {
  ESCALATION_REQUEST: { bg: "#FEF2F2", text: "#DC2626", border: "#FECACA" },
  UNRESOLVED:         { bg: "#FEF3C7", text: "#D97706", border: "#FDE68A" },
  FRAUD_SIGNAL:       { bg: "#FEF2F2", text: "#DC2626", border: "#FECACA", pulse: true },
  MANAGER_REQUEST:    { bg: "#FEF3C7", text: "#D97706", border: "#FDE68A" },
  MOOD_SHIFT:         { bg: "#FEFCE8", text: "#CA8A04", border: "#FEF08A" },
  REPEAT_CONTACT:     { bg: "#FAF5FF", text: "#9333EA", border: "#E9D5FF" },
  COMPLAINT:          { bg: "#FEF2F2", text: "#DC2626", border: "#FECACA" },
  LONG_SILENCE:       { bg: "#F8FAFC", text: "#64748B", border: "#E2E8F0" },
  OVERTALK:           { bg: "#F8FAFC", text: "#64748B", border: "#E2E8F0" },
  APOLOGY:            { bg: "#EFF6FF", text: "#2563EB", border: "#BFDBFE" },
  RESOLUTION_ATTEMPT: { bg: "#F0FDF4", text: "#16A34A", border: "#BBF7D0" },
  COMPLIANCE_BREACH:  { bg: "#FEF2F2", text: "#DC2626", border: "#FECACA" },
  POSITIVE_FEEDBACK:  { bg: "#F0FDF4", text: "#15803D", border: "#86EFAC" },
  HOLD_PLACED:        { bg: "#F5F3FF", text: "#7C3AED", border: "#DDD6FE" },
};

export function MomentBadge({ type, small }: { type: string; small?: boolean }) {
  const cfg = momentConfig[type as MomentType] ?? { bg: "#F8FAFC", text: "#64748B", border: "#E2E8F0" };
  const label = type.replace(/_/g, " ");
  return (
    <span
      className="inline-flex items-center gap-1 font-semibold rounded-md"
      style={{
        background: cfg.bg,
        color: cfg.text,
        border: `1px solid ${cfg.border}`,
        fontSize: small ? "10px" : "11px",
        padding: small ? "1px 6px" : "2px 8px",
        letterSpacing: "0.03em",
        whiteSpace: "nowrap",
      }}
    >
      {cfg.pulse && (
        <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: cfg.text }} />
      )}
      {label}
    </span>
  );
}

export function getMomentColor(type: string): string {
  const cfg = momentConfig[type as MomentType];
  return cfg?.text ?? "#64748B";
}

export function ScoreBadge({ score, large }: { score: number; large?: boolean }) {
  const color = score >= 80 ? "#DC2626" : score >= 60 ? "#D97706" : score >= 40 ? "#CA8A04" : "#16A34A";
  const bg    = score >= 80 ? "#FEF2F2" : score >= 60 ? "#FEF3C7" : score >= 40 ? "#FEFCE8" : "#F0FDF4";
  const border= score >= 80 ? "#FECACA" : score >= 60 ? "#FDE68A" : score >= 40 ? "#FEF08A" : "#BBF7D0";

  return (
    <span className="font-bold font-mono rounded-md"
      style={{
        background: bg, color, border: `1px solid ${border}`,
        fontSize: large ? "20px" : "13px",
        padding: large ? "4px 12px" : "2px 8px",
      }}>
      {score}
    </span>
  );
}

export function RiskBadge({ level }: { level: string }) {
  const configs: Record<string, { bg: string; text: string; border: string }> = {
    CRITICAL: { bg: "#FEF2F2", text: "#DC2626", border: "#FECACA" },
    HIGH:     { bg: "#FEF3C7", text: "#D97706", border: "#FDE68A" },
    MEDIUM:   { bg: "#FEFCE8", text: "#CA8A04", border: "#FEF08A" },
    LOW:      { bg: "#F0FDF4", text: "#16A34A", border: "#BBF7D0" },
  };
  const cfg = configs[level] ?? configs.MEDIUM;
  return (
    <span className="text-[11px] font-semibold rounded-md px-2 py-0.5 inline-block"
      style={{ background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}`, letterSpacing: "0.04em" }}>
      {level}
    </span>
  );
}

export function MoodArc({ startScore, endScore }: { startScore: number; endScore: number }) {
  const scoreToColor = (s: number) => s > 0.2 ? "#22C55E" : s > -0.3 ? "#F59E0B" : "#EF4444";
  const startColor = scoreToColor(startScore);
  const endColor = scoreToColor(endScore);
  return (
    <div className="flex items-center gap-1">
      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: startColor }} />
      <svg width="24" height="10" viewBox="0 0 24 10">
        <path d="M 0 5 Q 12 0 24 5" stroke={endColor} strokeWidth="1.5" fill="none" opacity="0.4" />
      </svg>
      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: endColor }} />
    </div>
  );
}
