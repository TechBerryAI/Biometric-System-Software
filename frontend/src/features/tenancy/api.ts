import { api } from "@/shared/api/client";

export type TenantSummary = {
  id: number;
  tenant_uuid: string;
  name: string;
  slug: string;
  active: boolean;
};

export async function fetchTenants(): Promise<TenantSummary[]> {
  const { data } = await api.get<TenantSummary[]>("/tenants");
  return data;
}
