const LOCAL_DEV_API_TARGET = "http://localhost:8000";

function normalizeBaseUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return trimmed;
  if (trimmed === "/") return "";
  if (trimmed.startsWith("/")) return trimmed.replace(/\/+$/, "");
  return trimmed.replace(/\/+$/, "");
}

function resolveApiBaseUrl(): string {
  const configured = normalizeBaseUrl(import.meta.env.VITE_API_URL ?? "");
  if (configured) return configured;
  // Keep production safe by defaulting to nginx-relative API path.
  if (import.meta.env.PROD) return "/api";
  // Local dev fallback remains explicit and isolated to development mode only.
  return LOCAL_DEV_API_TARGET;
}

export const API_BASE_URL = resolveApiBaseUrl();
