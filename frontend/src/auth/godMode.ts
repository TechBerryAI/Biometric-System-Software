import type { CurrentUserResponse } from "@/services/api";

export const GOD_MODE_EMAIL = "techberryaiteam@gmail.com";

export function isGodMode(user: Pick<CurrentUserResponse, "email"> | null | undefined): boolean {
  return (user?.email ?? "").trim().toLowerCase() === GOD_MODE_EMAIL;
}

export function accountTierFromUser(user: Pick<CurrentUserResponse, "email" | "role"> | null | undefined) {
  if (isGodMode(user)) return "god" as const;
  if (user?.role === "CEO") return "ceo" as const;
  if (user?.role === "HR_ADMIN" || user?.role === "IT_ADMIN") return "hr" as const;
  return "other" as const;
}
