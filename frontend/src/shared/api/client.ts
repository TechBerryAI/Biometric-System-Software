import axios from "axios";
import { API_BASE_URL } from "@/config/api";
import { getSelectedTenantId } from "@/stores/tenant-store";

const baseURL = API_BASE_URL;

export const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
  withCredentials: true,
});

export const rawApi = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
  withCredentials: true,
});

let accessToken: string | null = null;
let refreshHandler: (() => Promise<string | null>) | null = null;

export function configureApiAuth(token: string | null) {
  accessToken = token;
}

export function clearApiAuth() {
  accessToken = null;
}

export function registerTokenRefreshHandler(handler: () => Promise<string | null>) {
  refreshHandler = handler;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function attachSecurityHeaders(config: Record<string, unknown>) {
  if (accessToken) {
    config.Authorization = `Bearer ${accessToken}`;
  } else {
    delete config.Authorization;
  }
  const csrf = readCookie("csrf_token");
  if (csrf) {
    config["X-CSRF-Token"] = csrf;
  }
  const tenantId = getSelectedTenantId();
  if (tenantId != null) {
    config["x-tenant-id"] = String(tenantId);
  }
  return config;
}

api.interceptors.request.use((config) => {
  config.headers = attachSecurityHeaders(config.headers ?? {});
  return config;
});

rawApi.interceptors.request.use((config) => {
  config.headers = attachSecurityHeaders(config.headers ?? {});
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) throw error;
    const original = error.config as typeof error.config & { _retry?: boolean };
    if (!original || original._retry || !refreshHandler) throw error;
    original._retry = true;
    const token = await refreshHandler();
    if (token) {
      original.headers = original.headers ?? {};
      original.headers.Authorization = `Bearer ${token}`;
    }
    return api.request(original);
  }
);

/** Device pulls can take minutes on large terminals; keep this much higher than default API calls. */
export const SYNC_HTTP_TIMEOUT_MS = 600_000;

/** Grok narrative can be slower than typical CRUD calls. */
export const INSIGHTS_HTTP_TIMEOUT_MS = 90_000;

export function getApiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const raw = err.response?.data as { detail?: unknown } | undefined;
    if (typeof raw?.detail === "string") return raw.detail;
    if (Array.isArray(raw?.detail)) {
      return raw.detail
        .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x)))
        .join("; ");
    }
    if (err.response?.status === 409) {
      return "Device is busy with another sync. Wait a few seconds and try again.";
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Request failed";
}

export function formatSyncErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err) && err.response?.status === 504) {
    return "The VM proxy timed out while the device was still sending punches. Wait a minute and refresh — the sync may have finished in the background.";
  }
  const message = getApiErrorMessage(err);
  if (message.includes("no route to host")) {
    return `${message} You can still adjust attendance manually while the device is offline.`;
  }
  if (message.includes("busy") || message.includes("lock")) {
    return message;
  }
  return message;
}
