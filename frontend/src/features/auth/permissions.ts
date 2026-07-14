export type UserRole = "SUPER_ADMIN" | "HR_ADMIN" | "IT_ADMIN" | "CEO" | "MANAGER" | "VIEWER" | "DEVICE_OPERATOR";

export type Permission =
  | "dashboard:view"
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
    "dashboard:view",
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
  HR_ADMIN: ["dashboard:view", "employee:view", "employee:edit", "sync:trigger", "reports:read", "anomaly:manage"],
  IT_ADMIN: [
    "user:manage",
    "employee:view",
    "employee:edit",
    "sync:trigger",
    "reports:read",
    "anomaly:manage",
    "audit:read",
    "metrics:read",
  ],
  CEO: [
    "dashboard:view",
    "employee:view",
    "sync:trigger",
    "reports:read",
    "audit:read",
    "metrics:read",
  ],
  MANAGER: [],
  VIEWER: [],
  DEVICE_OPERATOR: [],
};

export function hasPermission(role: UserRole, permission: Permission): boolean {
  return rolePermissions[role].includes(permission);
}
