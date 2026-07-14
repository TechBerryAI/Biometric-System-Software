import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { createElement, type ReactElement, type ReactNode } from "react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";
import { AuthProvider } from "@/features/auth/AuthContext";

type Options = Omit<RenderOptions, "wrapper"> & {
  route?: string;
  initialEntries?: MemoryRouterProps["initialEntries"];
  withAuth?: boolean;
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(ui: ReactElement, options: Options = {}) {
  const { route = "/", initialEntries, withAuth = true, ...renderOptions } = options;
  const queryClient = createTestQueryClient();
  const entries = initialEntries ?? [route];

  function Wrapper({ children }: { children: ReactNode }) {
    const tree = createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(MemoryRouter, { initialEntries: entries }, children),
    );
    if (!withAuth) return tree;
    return createElement(AuthProvider, null, tree);
  }

  return {
    queryClient,
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  };
}
