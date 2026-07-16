import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { hasPermission, type Permission, type UserRole } from "./permissions";
import { clearApiAuth, configureApiAuth, registerTokenRefreshHandler } from "@/shared/api/client";
import {
  fetchCurrentUser,
  loginWithPassword,
  logoutSession,
  refreshSession,
  verifyMfaLogin,
  type AuthTokens,
  type LoginChallengeResponse,
} from "@/features/auth/api";

type SessionUser = {
  user_uuid: string;
  email: string;
  full_name?: string | null;
  role: UserRole;
  active: boolean;
};

type SessionState = {
  accessToken?: string;
  refreshToken?: string;
  refreshExpiresAt?: string;
  cookieAuth?: boolean;
};

type AuthContextValue = {
  user: SessionUser | null;
  loading: boolean;
  login: (email: string, password: string, mfaCode?: string) => Promise<void>;
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
    if (!parsed.accessToken && !parsed.refreshToken && !parsed.cookieAuth) return null;
    return parsed;
  } catch {
    return null;
  }
}

function persistSession(session: SessionState | null) {
  if (!session || (!session.accessToken && !session.refreshToken && !session.cookieAuth)) {
    localStorage.removeItem(SESSION_KEY);
    return;
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

function tokensToSession(tokens: AuthTokens): SessionState {
  const cookieAuth = !tokens.access_token && !tokens.refresh_token;
  return {
    accessToken: tokens.access_token ?? undefined,
    refreshToken: tokens.refresh_token ?? undefined,
    refreshExpiresAt: tokens.refresh_expires_at ?? undefined,
    cookieAuth,
  };
}

function isLoginChallenge(value: AuthTokens | LoginChallengeResponse): value is LoginChallengeResponse {
  return "challenge_token" in value && value.mfa_required === true;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [session, setSession] = useState<SessionState | null>(null);
  const [loading, setLoading] = useState(true);

  const applySession = useCallback((next: SessionState | null) => {
    setSession(next);
    persistSession(next);
    if (next?.accessToken) configureApiAuth(next.accessToken);
    else if (!next?.cookieAuth) clearApiAuth();
  }, []);

  const tryRefresh = useCallback(async () => {
    const refreshed = await refreshSession(session?.refreshToken);
    if (!refreshed) return false;
    const next = tokensToSession(refreshed);
    applySession(next.accessToken || next.refreshToken || next.cookieAuth ? next : { cookieAuth: true });
    return true;
  }, [applySession, session?.refreshToken]);

  useEffect(() => {
    registerTokenRefreshHandler(async () => {
      const refreshed = await tryRefresh();
      if (!refreshed) return null;
      return readStoredSession()?.accessToken ?? null;
    });
  }, [tryRefresh]);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      const stored = readStoredSession();
      if (stored?.accessToken) applySession(stored);
      else clearApiAuth();

      let me = await fetchCurrentUser();
      if (!me && stored?.refreshToken) {
        const refreshed = await refreshSession(stored.refreshToken);
        if (refreshed) {
          applySession(tokensToSession(refreshed));
          me = await fetchCurrentUser();
        }
      }
      if (!me && stored?.cookieAuth) {
        const refreshed = await refreshSession();
        if (refreshed) {
          applySession(tokensToSession(refreshed));
          me = await fetchCurrentUser();
        }
      }
      if (!me && stored) applySession(null);
      if (!cancelled) setUser(me as SessionUser | null);
      setLoading(false);
    };
    init();
    return () => {
      cancelled = true;
    };
  }, [applySession]);

  const login = useCallback(
    async (email: string, password: string, mfaCode?: string) => {
      const result = await loginWithPassword(email, password, mfaCode);
      if (isLoginChallenge(result)) {
        throw new Error("MFA verification required. Provide an authenticator code.");
      }
      applySession(tokensToSession(result));
      const me = await fetchCurrentUser();
      if (!me) throw new Error("Could not load current user after login.");
      setUser(me as SessionUser);
    },
    [applySession]
  );

  const logout = useCallback(async () => {
    await logoutSession(session?.refreshToken);
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
      applySession(tokensToSession(tokens));
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

export { verifyMfaLogin };
