import { describe, expect, it } from "vitest";
import { hasPermission } from "@/features/auth/permissions";

describe("FE-UNIT-PERM-001 permissions role matrix", () => {
  it("grants SUPER_ADMIN dashboard:view", () => {
    expect(hasPermission("SUPER_ADMIN", "dashboard:view")).toBe(true);
  });

  it("denies VIEWER employee:view", () => {
    expect(hasPermission("VIEWER", "employee:view")).toBe(false);
  });
});
