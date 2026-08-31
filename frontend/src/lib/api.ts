const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ── Response types (mirror backend Pydantic models) ──────────────────────────

export interface CallSummary {
  call_id: string;
  status: string;
  session: string | null;
  agent_name: string | null;
  customer_name: string | null;
  duration_seconds: number | null;
  risk_level: string | null;
  outcome: string | null;
  attention_score: number | null;
  qa_score: number | null;
  resolved: boolean | null;
  intent: string | null;
  topics: string[];
  moment_types: string[];
  mood_start: number | null;
  mood_end: number | null;
  top_moment_type: string | null;
  call_start_utc: string | null;
  label_caller_mos: number | null;
  label_agent_mos: number | null;
  created_at: string | null;
  processed_at: string | null;
}

export interface CallListResponse {
  total: number;
  page: number;
  page_size: number;
  items: CallSummary[];
}

export interface StatsResponse {
  total_calls: number;
  done_calls: number;
  failed_calls: number;
  pending_calls: number;
  processing_calls: number;
  avg_qa_score: number | null;
  avg_attention_score: number | null;
  resolved_count: number;
  unresolved_count: number;
  escalated_count: number;
  risk_breakdown: Record<string, number>;
  outcome_breakdown: Record<string, number>;
}

export interface MomentItem {
  moment_id: number;
  call_id: string;
  moment_type: string;
  severity: string;
  start_time: number;
  trigger_phrase: string;
  description: string | null;
  confidence: number | null;
}

export interface TurnItem {
  id: number;
  speaker: string;
  text: string;
  start_time: number;
  end_time: number;
  sentiment_score: number | null;
  moment_ids: number[];
}

export interface EvidenceItem {
  turn_id: number;
  speaker: string;
  quote: string;
  strength: string;
  claim: string | null;
  timestamp: number | null;
  confidence: number | null;
  moment_id: number | null;
  reasoning: string | null;
}

export interface AgentSummary {
  agent_name: string;
  call_count: number;
  avg_qa_score: number | null;
  avg_attention_score: number | null;
  resolution_rate: number;
  avg_handle_time: number | null;
}

export interface CustomerSummary {
  customer_name: string;
  total_calls: number;
  resolved_count: number;
  resolution_rate: number;
  avg_score: number | null;
  risk_level: string | null;
  last_call_at: string | null;
}

export interface TrendingIntent {
  intent: string;
  count: number;
}

export interface TrendDay {
  date: string;
  call_count: number;
  avg_score: number | null;
  resolution_rate: number;
}

// ── API functions ─────────────────────────────────────────────────────────────

export interface CallDetailResponse extends CallSummary {
  analysis: Record<string, unknown> | null;
}

export const api = {
  calls: {
    list: (params?: {
      page?: number;
      page_size?: number;
      agent_name?: string;
      status?: string;
      risk_level?: string;
      outcome?: string;
    }) => {
      const q = new URLSearchParams();
      if (params?.page) q.set("page", String(params.page));
      if (params?.page_size) q.set("page_size", String(params.page_size));
      if (params?.agent_name) q.set("agent_name", params.agent_name);
      if (params?.status) q.set("status", params.status);
      if (params?.risk_level) q.set("risk_level", params.risk_level);
      if (params?.outcome) q.set("outcome", params.outcome);
      return get<CallListResponse>(`/calls?${q}`);
    },
    stats: () => get<StatsResponse>("/calls/stats"),
    trendingIntents: (limit = 10) =>
      get<TrendingIntent[]>(`/calls/trending-intents?limit=${limit}`),
    trends: (days = 30) => get<TrendDay[]>(`/calls/trends?days=${days}`),
    detail: (callId: string) =>
      get<CallDetailResponse>(`/calls/${callId}`),
    transcript: (callId: string) =>
      get<{ call_id: string; total_turns: number; turns: TurnItem[] }>(
        `/calls/${callId}/transcript`
      ),
    moments: (callId: string) =>
      get<{ call_id: string; total: number; moments: MomentItem[] }>(
        `/calls/${callId}/moments`
      ),
    evidence: (callId: string) =>
      get<{ call_id: string; total: number; evidence: EvidenceItem[] }>(
        `/calls/${callId}/evidence`
      ),
    audioUrl: (callId: string) => `${BASE}/calls/${callId}/audio`,
    upload: async (file: File): Promise<{ call_id: string; status: string }> => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${BASE}/calls/upload`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error((err as { detail?: string }).detail ?? `Upload failed (${res.status})`);
      }
      return res.json() as Promise<{ call_id: string; status: string }>;
    },
  },
  agents: {
    list: () => get<AgentSummary[]>("/agents"),
    calls: (name: string, page = 1) =>
      get<CallListResponse>(`/agents/${encodeURIComponent(name)}/calls?page=${page}`),
    stats: (name: string) =>
      get<Record<string, unknown>>(`/agents/${encodeURIComponent(name)}/stats`),
  },
  customers: {
    list: () => get<CustomerSummary[]>("/customers"),
    calls: (name: string, page = 1) =>
      get<CallListResponse>(`/customers/${encodeURIComponent(name)}/calls?page=${page}`),
    profile: (name: string) =>
      get<Record<string, unknown>>(`/customers/${encodeURIComponent(name)}/profile`),
  },
};
