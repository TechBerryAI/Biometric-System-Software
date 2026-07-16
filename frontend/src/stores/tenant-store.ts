import { create } from "zustand";
import { persist } from "zustand/middleware";

type TenantStore = {
  selectedTenantId: number | null;
  setSelectedTenantId: (tenantId: number | null) => void;
};

export const useTenantStore = create<TenantStore>()(
  persist(
    (set) => ({
      selectedTenantId: null,
      setSelectedTenantId: (tenantId) => set({ selectedTenantId: tenantId }),
    }),
    { name: "biometrica-tenant" }
  )
);

export function getSelectedTenantId(): number | null {
  return useTenantStore.getState().selectedTenantId;
}
