import { api, configureApiAuth } from "@/shared/api/client";
import type { AccountCreatePayload, AuthTokens, CurrentUserResponse } from "@/features/auth/api";

export async function createAppAccount(payload: AccountCreatePayload): Promise<CurrentUserResponse> {
  const normalized = {
    email: payload.email.trim().toLowerCase(),
    full_name: payload.full_name?.trim() || null,
    password: payload.password,
    role: payload.role,
    active: payload.active ?? true,
  };
  const { data } = await api.post<CurrentUserResponse>("/auth/users", normalized);
  return data;
}

export async function updateMyProfile(payload: { full_name: string }): Promise<CurrentUserResponse> {
  const { data } = await api.put<CurrentUserResponse>("/auth/me", {
    full_name: payload.full_name.trim(),
  });
  return data;
}

export async function changeMyPassword(payload: {
  current_password: string;
  new_password: string;
  confirm_password: string;
}): Promise<AuthTokens> {
  const { data } = await api.post<AuthTokens>("/auth/me/password", payload);
  configureApiAuth(data.access_token);
  return data;
}
