import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { useAuth, USERS, initials } from "../context/AuthContext";

function RadarIcon({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="2" fill="white" />
      <path d="M12 12 L4 4" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="12" cy="12" r="5" stroke="white" strokeWidth="1.5" opacity="0.7" />
      <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="1.5" opacity="0.35" />
    </svg>
  );
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (!username.trim()) {
      setError("Please enter your username.");
      return;
    }

    const profile = USERS[username.trim().toLowerCase()];
    if (!profile) {
      setError("Username not recognised. Try james.davies, sarah.johnson, alex.kumar, or emma.wilson.");
      return;
    }

    setLoading(true);
    setTimeout(() => {
      login({
        id: username.trim().toLowerCase(),
        name: profile.name,
        title: profile.title,
        initials: initials(profile.name),
      });
      navigate("/", { replace: true });
    }, 600);
  };

  return (
    <div
      className="min-h-screen flex"
      style={{ background: "#F5F7FA" }}
    >
      {/* Left panel */}
      <div
        className="hidden lg:flex lg:w-[480px] flex-col justify-between p-12 flex-shrink-0"
        style={{
          background: "linear-gradient(145deg, #312E81 0%, #4F46E5 50%, #6366F1 100%)",
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(255,255,255,0.15)", backdropFilter: "blur(4px)" }}
          >
            <RadarIcon size={22} />
          </div>
          <div>
            <p className="font-bold text-white text-[17px] tracking-tight">Call Radar</p>
            <p className="text-[10px] font-mono" style={{ color: "rgba(255,255,255,0.55)" }}>
              AI · ANALYTICS
            </p>
          </div>
        </div>

        <div>
          <p
            className="text-[13px] font-semibold uppercase tracking-widest mb-4"
            style={{ color: "rgba(255,255,255,0.45)" }}
          >
            Call Centre Intelligence
          </p>
          <h1 className="text-[38px] font-bold text-white leading-tight mb-5">
            Every conversation,<br />fully understood.
          </h1>
          <p className="text-[15px] leading-relaxed" style={{ color: "rgba(255,255,255,0.7)" }}>
            Transcribe, analyse, and surface behavioural signals across every customer conversation — in real time.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.4)" }}>
            Powered by AI
          </span>
          <div className="flex-1 h-px" style={{ background: "rgba(255,255,255,0.15)" }} />
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-[400px]">
          {/* Mobile logo */}
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}
            >
              <RadarIcon size={20} />
            </div>
            <p className="font-bold text-[16px]" style={{ color: "#0F172A" }}>Call Radar</p>
          </div>

          <h2 className="text-[28px] font-bold mb-1" style={{ color: "#0F172A" }}>
            Sign in
          </h2>
          <p className="text-[14px] mb-8" style={{ color: "#64748B" }}>
            Enter your credentials to access the dashboard.
          </p>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-[12px] font-semibold mb-1.5" style={{ color: "#475569" }}>
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. james.davies"
                autoFocus
                className="w-full px-3.5 py-2.5 rounded-lg text-[14px] outline-none transition-all"
                style={{
                  background: "#FFFFFF",
                  border: "1px solid #E2E8F0",
                  color: "#0F172A",
                }}
                onFocus={(e) => (e.target.style.borderColor = "#6366F1")}
                onBlur={(e) => (e.target.style.borderColor = "#E2E8F0")}
              />
            </div>

            <div>
              <label className="block text-[12px] font-semibold mb-1.5" style={{ color: "#475569" }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3.5 py-2.5 rounded-lg text-[14px] outline-none transition-all"
                style={{
                  background: "#FFFFFF",
                  border: "1px solid #E2E8F0",
                  color: "#0F172A",
                }}
                onFocus={(e) => (e.target.style.borderColor = "#6366F1")}
                onBlur={(e) => (e.target.style.borderColor = "#E2E8F0")}
              />
            </div>

            {error && (
              <p
                className="text-[12px] px-3 py-2.5 rounded-lg"
                style={{ background: "#FEF2F2", color: "#DC2626", border: "1px solid #FECACA" }}
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg text-[14px] font-semibold text-white transition-all"
              style={{
                background: loading
                  ? "#A5B4FC"
                  : "linear-gradient(135deg, #6366F1, #4F46E5)",
                boxShadow: loading ? "none" : "0 2px 8px rgba(99,102,241,0.35)",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div
            className="mt-8 rounded-xl p-4"
            style={{ background: "#F8FAFC", border: "1px solid #E2E8F0" }}
          >
            <p className="text-[11px] font-semibold mb-2" style={{ color: "#94A3B8" }}>
              DEMO ACCOUNTS
            </p>
            <div className="space-y-1.5">
              {Object.entries(USERS).map(([id, { name, title }]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setUsername(id)}
                  className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left transition-all hover:bg-white"
                  style={{ color: "#475569" }}
                >
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0"
                    style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}
                  >
                    {initials(name)}
                  </div>
                  <div>
                    <p className="text-[12px] font-medium" style={{ color: "#0F172A" }}>{name}</p>
                    <p className="text-[10px]" style={{ color: "#94A3B8" }}>{title} · {id}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
