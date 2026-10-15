import type { CurrentUserResponse } from "@/features/auth/api";
import type { UserRole } from "@/features/auth/permissions";

export type UserCapability = "attendance_adjust" | "forensic_audit";

export type AccountTier = "operator" | "ceo" | "hr" | "other";

type CapabilityUser = Pick<CurrentUserResponse, "capabilities">;
// Session users carry the wider client-side role union; /auth/me roles are a subset of it.
type RoleCapabilityUser = CapabilityUser & { role: UserRole };

export function hasCapability(
  user: CapabilityUser | null | undefined,
  capability: UserCapability,
): boolean {
  return Boolean(user?.capabilities?.[capability]);
}

export function isOperatorAccount(
  user: CapabilityUser | null | undefined,
): boolean {
  return hasCapability(user, "attendance_adjust") || hasCapability(user, "forensic_audit");
}

export function accountTierFromUser(
  user: RoleCapabilityUser | null | undefined,
): AccountTier {
  // Elevated flag account keeps its distinct chrome; plain SUPER_ADMIN looks like IT/HR.
  if (isOperatorAccount(user)) return "operator";
  if (user?.role === "CEO") return "ceo";
  if (user?.role === "HR_ADMIN" || user?.role === "IT_ADMIN" || user?.role === "SUPER_ADMIN") {
    return "hr";
  }
  return "other";
}

export function roleLabelFromUser(
  user: RoleCapabilityUser | null | undefined,
): string {
  // Only the elevated in-session account shows this label — never offered at login or Add Account.
  if (isOperatorAccount(user)) return "GOD mode";
  switch (user?.role) {
    case "SUPER_ADMIN":
      return "IT Admin";
    case "CEO":
      return "CEO";
    case "IT_ADMIN":
      return "IT Admin";
    case "HR_ADMIN":
      return "HR Admin";
    default:
      return user?.role ?? "No role";
  }
}
