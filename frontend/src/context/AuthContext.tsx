import { createContext, useContext, useState, type ReactNode } from "react";

export interface AuthUser {
  id: string;
  name: string;
  title: string;
  initials: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  login: (user: AuthUser) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function initials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

export const USERS: Record<string, Omit<AuthUser, "id" | "initials">> = {
  "james.davies": { name: "James Davies", title: "Senior Manager" },
  "sarah.johnson": { name: "Sarah Johnson", title: "QA Analyst" },
  "alex.kumar": { name: "Alex Kumar", title: "Operations Manager" },
  "emma.wilson": { name: "Emma Wilson", title: "Team Lead" },
};

function readStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem("cr_user");
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(readStoredUser);

  const login = (u: AuthUser) => {
    localStorage.setItem("cr_user", JSON.stringify(u));
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem("cr_user");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { initials };
