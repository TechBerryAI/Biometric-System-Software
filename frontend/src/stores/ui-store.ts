import { create } from "zustand";
import { persist } from "zustand/middleware";

type UiState = {
  sidebarCollapsed: boolean;
  globalSearchQuery: string;
  setSidebarCollapsed: (v: boolean) => void;
  toggleSidebar: () => void;
  setGlobalSearchQuery: (v: string) => void;
};

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      globalSearchQuery: "",
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setGlobalSearchQuery: (globalSearchQuery) => set({ globalSearchQuery }),
    }),
    { name: "biometric-attendance-ui" }
  )
);
