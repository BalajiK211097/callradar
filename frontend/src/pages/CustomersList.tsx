import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Search, Phone, ChevronRight, ChevronLeft } from "lucide-react";
import { api, type CustomerSummary } from "../lib/api";
import { fmtTime, initials } from "../lib/format";
import { RiskBadge } from "../components/Badges";

const PAGE_SIZE = 10;

export default function CustomersList() {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.customers.list()
      .then(setCustomers)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // Reset to page 1 whenever search changes
  useEffect(() => { setPage(1); }, [search]);

  const filtered = customers.filter(c =>
    !search || c.customer_name.toLowerCase().includes(search.toLowerCase())
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-bold" style={{ color: "#0F172A" }}>Customers</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "#94A3B8" }}>
            {loading ? "Loading…" : `${filtered.length} of ${customers.length} customers`}
          </p>
        </div>
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#CBD5E1" }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search customers..."
            className="pl-9 pr-4 py-2 text-[13px] rounded-lg outline-none w-56"
            style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", color: "#0F172A" }}
          />
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-[13px]" style={{ color: "#94A3B8" }}>Loading customers…</div>
      ) : (
        /* Grid */
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {paginated.map(customer => {
            const resolutionRate = customer.total_calls > 0
              ? Math.round(customer.resolution_rate * 100)
              : 0;

            return (
              <div
                key={customer.customer_name}
                onClick={() => navigate(`/customers/${encodeURIComponent(customer.customer_name)}`)}
                className="card p-5 cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 group"
                style={{ borderColor: "#E2E8F0" }}
              >
                {/* Top: avatar + name + risk */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-full flex items-center justify-center text-[14px] font-bold flex-shrink-0"
                      style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", color: "white" }}
                    >
                      {initials(customer.customer_name)}
                    </div>
                    <div>
                      <p className="font-semibold text-[14px]" style={{ color: "#0F172A" }}>{customer.customer_name}</p>
                      <p className="text-[11px]" style={{ color: "#94A3B8" }}>
                        {customer.last_call_at ? `Last: ${fmtTime(customer.last_call_at)}` : "—"}
                      </p>
                    </div>
                  </div>
                  <RiskBadge level={customer.risk_level ?? "LOW"} />
                </div>

                {/* Stats row */}
                <div className="grid grid-cols-3 gap-2 mb-4">
                  {[
                    { label: "Total Calls", value: String(customer.total_calls) },
                    { label: "Resolved", value: `${customer.resolved_count}/${customer.total_calls}` },
                    {
                      label: "Rate",
                      value: `${resolutionRate}%`,
                      color: resolutionRate >= 80 ? "#16A34A" : resolutionRate >= 60 ? "#D97706" : "#DC2626",
                    },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="text-center py-2 rounded-lg" style={{ background: "#F8FAFC" }}>
                      <p className="text-[10px] uppercase tracking-wider mb-0.5" style={{ color: "#94A3B8" }}>{label}</p>
                      <p className="font-bold text-[14px]" style={{ color: color ?? "#0F172A" }}>{value}</p>
                    </div>
                  ))}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between pt-3" style={{ borderTop: "1px solid #F1F5F9" }}>
                  <div className="flex items-center gap-1.5 text-[12px]" style={{ color: "#94A3B8" }}>
                    <Phone size={11} />
                    <span>Avg score: {customer.avg_score ?? "—"}</span>
                  </div>
                  <span
                    className="flex items-center gap-1 text-[12px] font-medium opacity-0 group-hover:opacity-100 transition-all"
                    style={{ color: "#6366F1" }}
                  >
                    View profile <ChevronRight size={13} />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="text-center py-16">
          <p className="text-[15px] font-medium" style={{ color: "#94A3B8" }}>No customers match "{search}"</p>
          <button onClick={() => setSearch("")} className="text-[13px] mt-2" style={{ color: "#6366F1" }}>
            Clear search
          </button>
        </div>
      )}

      {/* Pagination */}
      {!loading && totalPages > 1 && (
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
    </div>
  );
}
