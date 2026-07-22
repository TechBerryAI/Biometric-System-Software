"""Internal device write / correction policy.

These flags are not env-configurable. Change them here (and redeploy) when
site policy must change — they deliberately do not appear in .env.
"""

from __future__ import annotations

# When True, Tier B firmware may use guarded full attlog rewrite with readback.
# Keep False: pyzk cannot commit attlog uploads on real ZK/ESSL firmware (clear
# would wipe device memory without restoring punches).
ATTLOG_TIER_B_REWRITE: bool = False

# Hard stop: never call clear_attendance / clear_data on the terminal.
# Punches must remain on the device until confirmed in attendance_logs via sync.
ALLOW_DEVICE_ATTLOG_CLEAR: bool = False

# When False, all device write / enqueue paths are blocked (cutover freeze).
DEVICE_WRITES_ENABLED: bool = True

# Upsert safety gates (admin_override payload still requires ADMIN_OVERRIDE).
UID_REWRITE: bool = False
PRIVILEGE_UPDATE: bool = False
CARD_REWRITE: bool = False
ADMIN_OVERRIDE: bool = False
