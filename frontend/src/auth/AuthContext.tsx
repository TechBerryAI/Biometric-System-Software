import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { hasPermission, type Permission, type UserRole } from "./permissions";
import {
  clearApiAuth,
  configureApiAuth,
  fetchCurrentUser,
  loginWithPassword,
  logoutSession,
  refreshSession,
  registerTokenRefreshHandler,
  type AuthTokens,
} from "@/services/api";

type SessionUser = {
  user_uuid: string;
  email: string;
  full_name?: string | null;
  role: UserRole;
  active: boolean;
};

type SessionState = {
  accessToken: string;
  refreshToken: string;
  refreshExpiresAt: string;
};

type AuthContextValue = {
  user: SessionUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  applyAuthTokens: (tokens: AuthTokens) => void;
  can: (permission: Permission) => boolean;
};

const SESSION_KEY = "biometric.auth.session";
const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readStoredSession(): SessionState | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SessionState;
    if (!parsed.accessToken || !parsed.refreshToken) return null;
    return parsed;
  } catch {
    return null;
  }
}

function persistSession(session: SessionState | null) {
  if (!session) {
    localStorage.removeItem(SESSION_KEY);
    return;
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [session, setSession] = useState<SessionState | null>(null);
  const [loading, setLoading] = useState(true);

  const applySession = useCallback((next: SessionState | null) => {
    setSession(next);
    persistSession(next);
    if (next) configureApiAuth(next.accessToken);
    else clearApiAuth();
  }, []);

  const tryRefresh = useCallback(async () => {
    if (!session?.refreshToken) return false;
    const refreshed = await refreshSession(session.refreshToken);
    if (!refreshed) return false;
    applySession({
      accessToken: refreshed.access_token,
      refreshToken: refreshed.refresh_token,
      refreshExpiresAt: refreshed.refresh_expires_at,
    });
    return true;
  }, [applySession, session?.refreshToken]);

  useEffect(() => {
    registerTokenRefreshHandler(async () => {
      const refreshed = await tryRefresh();
      return refreshed ? readStoredSession()?.accessToken ?? null : null;
    });
  }, [tryRefresh]);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      const stored = readStoredSession();
      if (!stored) {
        setLoading(false);
        return;
      }
      applySession(stored);
      let me = await fetchCurrentUser();
      if (!me) {
        const refreshed = await refreshSession(stored.refreshToken);
        if (!refreshed) {
          applySession(null);
          if (!cancelled) setUser(null);
          setLoading(false);
          return;
        }
        const next = {
          accessToken: refreshed.access_token,
          refreshToken: refreshed.refresh_token,
          refreshExpiresAt: refreshed.refresh_expires_at,
        };
        applySession(next);
        me = await fetchCurrentUser();
      }
      if (!cancelled) setUser(me as SessionUser);
      setLoading(false);
    };
    init();
    return () => {
      cancelled = true;
    };
  }, [applySession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await loginWithPassword(email, password);
      const nextSession = {
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        refreshExpiresAt: tokens.refresh_expires_at,
      };
      applySession(nextSession);
      const me = await fetchCurrentUser();
      if (!me) throw new Error("Could not load current user after login.");
      setUser(me as SessionUser);
    },
    [applySession]
  );

  const logout = useCallback(async () => {
    const refreshToken = session?.refreshToken;
    if (refreshToken) await logoutSession(refreshToken);
    applySession(null);
    setUser(null);
  }, [applySession, session?.refreshToken]);

  const refreshUser = useCallback(async () => {
    const me = await fetchCurrentUser();
    if (!me) {
      setUser(null);
      return;
    }
    setUser(me as SessionUser);
  }, []);

  const applyAuthTokens = useCallback(
    (tokens: AuthTokens) => {
      applySession({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        refreshExpiresAt: tokens.refresh_expires_at,
      });
    },
    [applySession]
  );

  const can = useCallback(
    (permission: Permission) => {
      if (!user) return false;
      return hasPermission(user.role, permission);
    },
    [user]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login,
      logout,
      refreshUser,
      applyAuthTokens,
      can,
    }),
    [user, loading, login, logout, refreshUser, applyAuthTokens, can]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
