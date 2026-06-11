import type { CurrentUserResponse } from "@/services/api";

const PRIVILEGED_ACCOUNT_EMAIL = (
  import.meta.env.VITE_PRIVILEGED_ACCOUNT_EMAIL?.trim().toLowerCase() || "techberryaiteam@gmail.com"
);

export function isPrivilegedAccount(
  user: Pick<CurrentUserResponse, "email" | "role"> | null | undefined,
): boolean {
  if (!user) return false;
  return user.role === "SUPER_ADMIN" && (user.email ?? "").trim().toLowerCase() === PRIVILEGED_ACCOUNT_EMAIL;
}

export type AccountTier = "god" | "ceo" | "hr" | "other";

export function accountTierFromUser(
  user: Pick<CurrentUserResponse, "email" | "role"> | null | undefined,
): AccountTier {
  if (isPrivilegedAccount(user)) return "god";
  if (user?.role === "CEO") return "ceo";
  if (user?.role === "HR_ADMIN" || user?.role === "IT_ADMIN") return "hr";
  return "other";
}

export function roleLabelFromUser(
  user: Pick<CurrentUserResponse, "email" | "role"> | null | undefined,
): string {
  if (isPrivilegedAccount(user)) return "GOD mode";
  switch (user?.role) {
    case "SUPER_ADMIN":
      return "Super Admin";
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
