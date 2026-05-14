export type UserRole = "SUPER_ADMIN" | "HR_ADMIN" | "MANAGER" | "VIEWER" | "DEVICE_OPERATOR";

export type Permission =
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
    "employee:edit",
    "device:manage",
    "sync:trigger",
    "ai:admin",
    "reports:read",
    "audit:read",
    "metrics:read",
    "anomaly:manage",
  ],
  HR_ADMIN: ["employee:edit", "sync:trigger", "reports:read", "anomaly:manage"],
  MANAGER: ["reports:read", "ai:admin", "anomaly:manage"],
  VIEWER: ["reports:read"],
  DEVICE_OPERATOR: ["device:manage", "sync:trigger", "metrics:read"],
};

export function hasPermission(role: UserRole, permission: Permission): boolean {
  return rolePermissions[role].includes(permission);
}
