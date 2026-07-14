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
  access_token: string;
  token_type: "bearer";
  refresh_token: string;
  refresh_expires_at: string;
  role: string;
};

export async function loginWithPassword(email: string, password: string): Promise<AuthTokens> {
  const { data } = await rawApi.post<AuthTokens>("/auth/login", { email, password });
  configureApiAuth(data.access_token);
  return data;
}

export async function refreshSession(refreshToken: string): Promise<AuthTokens | null> {
  try {
    const { data } = await rawApi.post<AuthTokens>("/auth/refresh", { refresh_token: refreshToken });
    configureApiAuth(data.access_token);
    return data;
  } catch {
    return null;
  }
}

export async function logoutSession(refreshToken: string): Promise<void> {
  try {
    await api.post("/auth/logout", { refresh_token: refreshToken });
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
