import { describe, expect, it } from "vitest";
import {
  accountTierFromUser,
  hasCapability,
  isOperatorAccount,
  roleLabelFromUser,
} from "@/features/auth/sessionCapabilities";

describe("FE-UNIT-CAP-001 sessionCapabilities", () => {
  const operator = {
    role: "SUPER_ADMIN" as const,
    capabilities: { attendance_adjust: true, forensic_audit: true },
  };

  it("labels elevated session as GOD mode; never exposes SUPER_ADMIN title", () => {
    expect(hasCapability(operator, "attendance_adjust")).toBe(true);
    expect(isOperatorAccount(operator)).toBe(true);
    expect(accountTierFromUser(operator)).toBe("operator");
    expect(roleLabelFromUser(operator)).toBe("GOD mode");
    expect(
      roleLabelFromUser({
        role: "SUPER_ADMIN",
        capabilities: { attendance_adjust: false, forensic_audit: false },
      }),
    ).toBe("IT Admin");
  });

  it("maps CEO and HR tiers without operator caps", () => {
    expect(
      accountTierFromUser({
        role: "CEO",
        capabilities: { attendance_adjust: false, forensic_audit: false },
      }),
    ).toBe("ceo");
    expect(
      accountTierFromUser({
        role: "HR_ADMIN",
        capabilities: { attendance_adjust: false, forensic_audit: false },
      }),
    ).toBe("hr");
    expect(hasCapability(null, "forensic_audit")).toBe(false);
  });
});
