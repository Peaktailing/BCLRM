import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import type { User, Role } from "@/data/mock";

const STORAGE_KEY = "reagent_lab_user";

interface AuthContextValue {
  user: User | null;
  login: (user: User) => void;
  logout: () => void;
  role: Role | "guest";
  can: (perm: string) => boolean;
}

const PERMISSIONS: Record<Role, string[]> = {
  super_admin: ["view", "manage_users", "system_settings", "edit_all", "delete_all"],
  admin: ["view", "add_reagent", "edit_own", "delete_own", "borrow", "approve_own"],
  teacher: ["view", "borrow"],
  student: ["view"],
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      try { setUser(JSON.parse(saved)); } catch { /* ignore */ }
    }
  }, []);

  const login = (u: User) => {
    setUser(u);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(u));
  };

  const logout = () => {
    setUser(null);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  const role = user?.role ?? "guest";

  const can = (perm: string): boolean => {
    if (role === "guest") return perm === "view";
    return PERMISSIONS[role]?.includes(perm) ?? false;
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, role, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
