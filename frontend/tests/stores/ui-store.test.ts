import { beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/stores/ui-store";

describe("FE-UNIT-STORE-001 ui-store", () => {
  beforeEach(() => {
    useUiStore.setState({
      sidebarCollapsed: false,
      globalSearchQuery: "",
    });
  });

  it("toggles sidebar and updates search query", () => {
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    useUiStore.getState().setGlobalSearchQuery("ada");
    expect(useUiStore.getState().globalSearchQuery).toBe("ada");
  });
});
