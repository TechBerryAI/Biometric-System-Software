import { api, rawApi, configureApiAuth } from "@/shared/api/client";

export type UserCapabilities = {
  attendance_adjust: boolean;
  forensic_audit: boolean;
};

export type CurrentUserResponse = {
  user_uuid: string;
  email: string;
  full_name?: string | null;
  role: "SUPER_ADMIN" | "HR_ADMIN" | "IT_ADMIN" | "CEO";
  active: boolean;
  mfa_enabled?: boolean;
  capabilities?: UserCapabilities;
};

export type AppUserRole = "HR_ADMIN" | "IT_ADMIN";

export type AccountCreatePayload = {
  email: string;
  full_name?: string;
  password: string;
  role: AppUserRole;
  active?: boolean;
};

export type AuthTokens = {
  access_token?: string | null;
  token_type: "bearer";
  refresh_token?: string | null;
  refresh_expires_at?: string | null;
  role: string;
  mfa_required?: boolean;
};

export type LoginChallengeResponse = {
  mfa_required: true;
  challenge_token: string;
  role: string;
};

export async function loginWithPassword(
  email: string,
  password: string,
  mfaCode?: string
): Promise<AuthTokens | LoginChallengeResponse> {
  const payload: Record<string, string> = { email, password };
  if (mfaCode) payload.mfa_code = mfaCode;
  const { data } = await rawApi.post<AuthTokens | LoginChallengeResponse>("/auth/login", payload);
  if ("access_token" in data && data.access_token) configureApiAuth(data.access_token);
  return data;
}

export async function verifyMfaLogin(challengeToken: string, mfaCode: string): Promise<AuthTokens | null> {
  try {
    const { data } = await rawApi.post<AuthTokens>("/auth/mfa/verify", {
      challenge_token: challengeToken,
      mfa_code: mfaCode,
    });
    if (data.access_token) configureApiAuth(data.access_token);
    return data;
  } catch {
    return null;
  }
}

export async function refreshSession(refreshToken?: string): Promise<AuthTokens | null> {
  try {
    const payload = refreshToken ? { refresh_token: refreshToken } : {};
    const { data } = await rawApi.post<AuthTokens>("/auth/refresh", payload);
    if (data.access_token) configureApiAuth(data.access_token);
    return data;
  } catch {
    return null;
  }
}

export async function logoutSession(refreshToken?: string): Promise<void> {
  try {
    const payload = refreshToken ? { refresh_token: refreshToken } : {};
    await api.post("/auth/logout", payload);
  } catch {
    // no-op, local session should still be cleared
  }
}

export async function fetchCurrentUser(): Promise<CurrentUserResponse | null> {
  try {
    const { data } = await api.get<CurrentUserResponse>("/auth/me");
    return data;
  } catch {
    return null;
  }
}
