import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import axios from "axios";
import type { ReactNode } from "react";
import { useState } from "react";

/**
 * Retry only failures that are likely to clear up on their own: no response (network blip),
 * 502/503/504 (API restarting, database briefly unavailable), and 429. Client errors such as
 * 401/403/404 fail immediately instead of making the user wait for pointless retries.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 3) return false;
  if (!axios.isAxiosError(error)) return failureCount < 1;
  const status = error.response?.status;
  return status === undefined || status === 429 || status === 502 || status === 503 || status === 504;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            retry: shouldRetry,
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
            refetchOnWindowFocus: false,
          },
        },
      })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
