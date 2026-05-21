export type UserRole = "SUPER_ADMIN" | "HR_ADMIN" | "CEO" | "MANAGER" | "VIEWER" | "DEVICE_OPERATOR";

export type Permission =
  | "user:manage"
  | "employee:view"
  | "employee:edit"
  | "device:manage"
  | "sync:trigger"
  | "ai:admin"
  | "reports:read"
  | "audit:read"
  | "metrics:read"
  | "anomaly:manage";

const rolePermissions: Record<UserRole, Permission[]> = {
  SUPER_ADMIN: [
    "user:manage",
    "employee:view",
    "employee:edit",
    "device:manage",
    "sync:trigger",
    "ai:admin",
    "reports:read",
    "audit:read",
    "metrics:read",
    "anomaly:manage",
  ],
  HR_ADMIN: ["employee:view", "employee:edit", "sync:trigger", "reports:read", "anomaly:manage"],
  CEO: ["employee:view", "reports:read"],
  MANAGER: [],
  VIEWER: [],
  DEVICE_OPERATOR: [],
};

export function hasPermission(role: UserRole, permission: Permission): boolean {
  return rolePermissions[role].includes(permission);
}
