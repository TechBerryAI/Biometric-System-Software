# Master Traceability Matrix

Maps every backend endpoint, model, service surface, Celery task, AI module, frontend page/API export, and biometric workflow to ≥1 automated test ID.  
IDs are reserved in this document; implementations live under `backend/tests/`, `frontend/src/**/*.test.*`, and `e2e/`.

Legend: **ID** = stable test marker · **File** = intended test module · **Status** `Required` until green in CI.

---

## 1. HTTP routes (43)

### Health (`app/main.py`)

| Surface | Test ID | File |
|---------|---------|------|
| `GET /health` | BE-API-HLTH-001 | `backend/tests/api/test_health_api.py` |
| `GET /health/db` | BE-API-HLTH-002 | same |
| `GET /health/redis` | BE-API-HLTH-003 | same |
| `GET /health/devices` | BE-API-HLTH-004 | same |
| `GET /health/ai` | BE-API-HLTH-005 | same |
| `GET /health/queue` | BE-API-HLTH-006 | same |
| `GET /health/reconciliation` | BE-API-HLTH-007 | same |
| Health authz deny | BE-API-HLTH-008 | same |

### Auth (`app/api/auth.py`)

| Surface | Test ID | File |
|---------|---------|------|
| `POST /auth/bootstrap-admin` | BE-API-AUTH-001 | `backend/tests/api/test_auth_api.py` |
| `POST /auth/login` | BE-API-AUTH-002 | same |
| `POST /auth/refresh` | BE-API-AUTH-003 | same |
| `POST /auth/logout` | BE-API-AUTH-004 | same |
| `GET /auth/me` | BE-API-AUTH-005 | same |
| `PUT /auth/me` | BE-API-AUTH-006 | same |
| `POST /auth/me/password` | BE-API-AUTH-007 | same |
| `POST /auth/users` | BE-API-AUTH-008 | same |
| Auth unauthorized / validation | BE-API-AUTH-009 | same |
| Login rate limit | BE-UNIT-AUTH-010 | `backend/tests/unit/test_auth_service.py` |
| `POST /auth/forgot-password` | BE-API-AUTH-011 | `backend/tests/api/test_auth_api.py` |
| `POST /auth/reset-password` | BE-API-AUTH-012 | same |

### Employees (`app/api/employee.py`)

| Surface | Test ID | File |
|---------|---------|------|
| `GET /employees` | BE-API-EMP-001 | `backend/tests/api/test_employee_api.py` |
| `GET /employees/{id}` | BE-API-EMP-002 | same |
| `POST /employees` | BE-API-EMP-003 | same |
| `PUT /employees/{id}` | BE-API-EMP-004 | same |
| `DELETE /employees/{id}` | BE-API-EMP-005 | same |
| `GET /employees/{id}/daily-attendance` | BE-API-EMP-006 | same |
| Emp authz deny | BE-API-EMP-007 | same |
| Dept/shift field persistence | BE-UNIT-EMP-DEPT-001 | `backend/tests/unit/test_department_shift_fields.py` |

### Attendance (`app/api/attendance.py`)

| Surface | Test ID | File |
|---------|---------|------|
| `GET /attendance/logs` | BE-API-ATT-001 | `backend/tests/api/test_attendance_api.py` |
| `GET /attendance/sessions` | BE-API-ATT-002 | same |
| `GET /attendance/daily-summary` | BE-API-ATT-003 | same |
| `GET /attendance/daily-summary/range` | BE-API-ATT-004 | same |
| `GET /attendance/{employee_id}` | BE-API-ATT-005 | same |

### Attendance adjust (`app/api/attendance_correction.py`)

| Surface | Test ID | File |
|---------|---------|------|
| `GET /attendance/adjust/capabilities` | BE-API-ADJ-001 | `backend/tests/api/test_attendance_correction_api.py` |
| `GET /attendance/adjust/commands/{uuid}` | BE-API-ADJ-002 | same |
| `GET /attendance/adjust/day/{employee_id}` | BE-API-ADJ-003 | same |
| `POST /attendance/adjust/correct` | BE-API-ADJ-004 | same |
| Non-operator forbidden | BE-API-ADJ-005 | same |

### Sync / Insights / Ops

| Surface | Test ID | File |
|---------|---------|------|
| `POST /sync/device` | BE-API-SYNC-001 | `backend/tests/api/test_sync_api.py` |
| `POST /sync/device?wait=false` | BE-API-SYNC-003 | same |
| `GET /sync/jobs/{task_id}` | BE-API-SYNC-004 | same |
| `GET /insights/management` | BE-API-INS-001 | `backend/tests/api/test_insights_api.py` |
| `GET /insights/anomalies` | BE-API-INS-002 | same |
| Insights degrade without key | BE-API-INS-003 | same |
| `GET /ops/device-commands` | BE-API-OPS-001 | `backend/tests/api/test_operations_api.py` |
| `POST /ops/device-commands/{uuid}/process` | BE-API-OPS-002 | same |
| `GET /ops/metrics` | BE-API-OPS-003 | same |

---

## 2. ORM models (10)

| Model / table | Test ID | File |
|---------------|---------|------|
| `Employee` / `employees` | BE-INT-MDL-001 | `backend/tests/integration/test_employee_device_upsert.py` |
| `AttendanceLog` / `attendance_logs` | BE-INT-MDL-002 | `backend/tests/integration/test_device_sync_pipeline.py` |
| `AttendanceSession` / `attendance_sessions` | BE-INT-MDL-003 | same |
| `DeviceUserMapping` / `device_user_mappings` | BE-INT-MDL-004 | `backend/tests/integration/test_employee_offboard.py` |
| `User` / `users` | BE-API-AUTH-001 | `backend/tests/api/test_auth_api.py` |
| `RefreshToken` / `refresh_tokens` | BE-API-AUTH-003 | same |
| `PasswordResetToken` / `password_reset_tokens` | BE-API-AUTH-011 | same |
| `Device` / `devices` | BE-INT-MDL-005 | `backend/tests/integration/test_governance_blocks_writes.py` |
| `DeviceCommand` / `device_commands` | BE-INT-MDL-006 | `backend/tests/integration/test_command_retry_deadletter.py` |
| `SystemControlState` / `system_control_state` | BE-UNIT-GOV-001 | `backend/tests/unit/test_governance.py` |

---

## 3. Core / services / AI (selected public surfaces)

| Module | Surface | Test ID | File |
|--------|---------|---------|------|
| `core/security.py` | RBAC matrix | BE-UNIT-SEC-001 | `backend/tests/unit/test_security_rbac.py` |
| `core/operator_access.py` | operator flags | BE-UNIT-OPS-ACC-001 | `backend/tests/unit/test_operator_access.py` |
| `core/device_policy.py` | safe write / UID | BE-UNIT-POL-001 | `backend/tests/unit/test_device_policy.py` |
| `auth_service.py` | authenticate / tokens / bootstrap | BE-UNIT-AUTH-001 | `backend/tests/unit/test_auth_service.py` |
| `punch_classification.py` | classify / summarize / OT types | BE-UNIT-PUNCH-001 | `backend/tests/unit/test_punch_classification.py` |
| `attendance_helpers.py` | pair / rebuild / day bounds | BE-UNIT-HELP-001 | `backend/tests/unit/test_attendance_helpers.py` |
| `attendance_service.py` | idempotent insert / sync | BE-UNIT-IDEM-001 | `backend/tests/unit/test_attendance_idempotency.py` |
| `daily_summary_service.py` | compute summary | BE-UNIT-SUM-001 | `backend/tests/unit/test_daily_summary.py` |
| `device_attlog_codec.py` | encode/decode | BE-UNIT-CODEC-001 | `backend/tests/unit/test_attlog_codec.py` |
| `device_attlog_protocol.py` | Tier A/B/C | BE-UNIT-PROTO-001 | `backend/tests/unit/test_attlog_protocol.py` |
| `attendance_correction_service.py` | apply / finalize | BE-INT-CORR-001 | `backend/tests/integration/test_correction_device_first.py` |
| `attendance_lock_service.py` | employee_day_lock | BE-INT-LOCK-001 | `backend/tests/integration/test_locks_and_races.py` |
| `device_command_service.py` | enqueue/claim/process | BE-INT-CMD-001 | `backend/tests/integration/test_command_retry_deadletter.py` |
| `device_registry_service.py` | ensure/reconcile | BE-WRK-REC-001 | `backend/tests/workers/test_reconcile_task.py` |
| `employee_offboard_service.py` | offboard / keep list | BE-INT-OFF-001 | `backend/tests/integration/test_employee_offboard.py` |
| `employee_identity.py` | identity_filter | BE-UNIT-IDENT-001 | `backend/tests/unit/test_employee_identity.py` |
| `system_governance_service.py` | assert write allowed | BE-UNIT-GOV-001 | `backend/tests/unit/test_governance.py` |
| `constants/keep_list.py` | roster match | BE-UNIT-KEEP-001 | `backend/tests/unit/test_keep_list_matching.py` |
| `device_exceptions.py` | typed errors | BE-UNIT-EXC-001 | `backend/tests/unit/test_device_exceptions.py` |
| `pyzk_adapter.py` | retry/disconnect | BE-UNIT-ADAPT-001 | `backend/tests/unit/test_pyzk_adapter.py` |
| `management_insight_context.py` | build context | BE-UNIT-AI-CTX-001 | `backend/tests/unit/test_management_insight_context.py` |
| `ai/.../insight_service.py` | management insights | BE-UNIT-AI-INS-001 | `backend/tests/unit/test_insight_service.py` |
| `ai/.../anomaly_service.py` | detect + overtime_spike | BE-UNIT-AI-ANOM-001 | `backend/tests/unit/test_anomaly_heuristics.py` |
| `ai/.../grok_provider.py` | complete_json errors | BE-UNIT-AI-GROK-001 | `backend/tests/unit/test_grok_provider.py` |
| `ai/.../json_parser.py` | extract_json_payload | BE-UNIT-AI-JSON-001 | `backend/tests/unit/test_ai_json_parser.py` |
| `ai/.../governance.py` | assert_allowed | BE-UNIT-AI-GOV-001 | `backend/tests/unit/test_ai_governance.py` |
| `ai/.../redis_cache.py` | get/set/delete | BE-UNIT-AI-CACHE-001 | `backend/tests/unit/test_ai_cache.py` |

---

## 4. Celery tasks and beat

| Task / beat | Test ID | File |
|-------------|---------|------|
| `sync_attendance_from_device` | BE-WRK-SYNC-001 | `backend/tests/workers/test_sync_task.py` |
| `run_manual_device_sync` | BE-WRK-SYNC-002 | same |
| `probe_device_connectivity` | BE-WRK-PROBE-001 | `backend/tests/workers/test_probe_task.py` |
| `process_device_commands` | BE-WRK-CMD-001 | `backend/tests/workers/test_process_commands_task.py` |
| `reconcile_devices` | BE-WRK-REC-001 | `backend/tests/workers/test_reconcile_task.py` |
| `recover_stale_commands` | BE-WRK-STALE-001 | `backend/tests/workers/test_recover_stale_task.py` |
| Beat schedule entries | BE-WRK-BEAT-001 | `backend/tests/workers/test_beat_schedule.py` |

---

## 5. Biometric / device workflows

| Workflow | Test ID | File |
|----------|---------|------|
| Full sync → logs → sessions | BE-INT-SYNC-001 | `backend/tests/integration/test_device_sync_pipeline.py` |
| Offline then resync | BE-INT-OFFLINE-001 | `backend/tests/integration/test_offline_device_resync.py` |
| Duplicate prevention | BE-INT-DUP-001 | `backend/tests/integration/test_duplicate_prevention.py` |
| UPSERT verify | BE-INT-UPSERT-001 | `backend/tests/integration/test_employee_device_upsert.py` |
| Offboard DELETE verify | BE-INT-OFF-001 | `backend/tests/integration/test_employee_offboard.py` |
| Correction Tier A device-first | BE-INT-CORR-001 | `backend/tests/integration/test_correction_device_first.py` |
| Correction Tier C DB-only | BE-INT-CORR-002 | `backend/tests/integration/test_correction_db_only_fallback.py` |
| Command retry / dead-letter | BE-INT-CMD-002 | `backend/tests/integration/test_command_retry_deadletter.py` |
| Stale heartbeat recovery | BE-INT-STALE-001 | `backend/tests/integration/test_stale_command_recovery.py` |
| Locks / concurrent correct | BE-INT-LOCK-001 | `backend/tests/integration/test_locks_and_races.py` |
| Governance blocks writes | BE-INT-GOV-001 | `backend/tests/integration/test_governance_blocks_writes.py` |
| DB transaction rollback | BE-INT-TXN-001 | `backend/tests/integration/test_db_transactions.py` |
| Company operations day (API) | BE-SCN-DAY-001 | `backend/tests/e2e_scenarios/test_company_operations_day.py` |

---

## 6. Scripts (`backend/scripts/`)

| Script | Test ID | File / note |
|--------|---------|-------------|
| `sync_from_device.py` | BE-UNIT-SCR-001 | Import/smoke in `backend/tests/unit/test_scripts_smoke.py` |
| `probe_device_attlog_tier.py` | BE-UNIT-SCR-002 | same |
| `restore_device_normal_mode.py` | BE-UNIT-SCR-003 | same |
| `purge_departed_employees.py` | BE-UNIT-SCR-004 | same |
| `reset_user_password.py` | BE-UNIT-SCR-005 | same |
| `setup_local_database.sql` | N/A | Manual DBA artifact |

---

## 7. Frontend routes / pages

| Route / page | Test ID | File |
|--------------|---------|------|
| `/login` Login | FE-UNIT-LOGIN-001 | `frontend/src/pages/Login.test.tsx` |
| `/forgot-password` | FE-UNIT-FORGOT-001 | `frontend/tests/features/auth/pages/ForgotPasswordPage.test.tsx` |
| `/reset-password` | FE-UNIT-RESET-001 | `frontend/tests/features/auth/pages/ResetPasswordPage.test.tsx`
| `/` Dashboard | FE-UNIT-DASH-001 | `frontend/src/pages/Dashboard.test.tsx` |
| `/employees` | FE-UNIT-EMP-001 | `frontend/src/pages/Employees.test.tsx` |
| `/employees/:id` | FE-UNIT-EMP-002 | `frontend/src/pages/EmployeeProfile.test.tsx` |
| `/attendance` | FE-UNIT-ATT-001 | `frontend/src/pages/Attendance.test.tsx` |
| `/reports` | FE-UNIT-REP-001 | `frontend/src/pages/Reports.test.tsx` |
| `/operations` | FE-UNIT-OPS-001 | `frontend/src/pages/Operations.test.tsx` |
| `/audit` | FE-UNIT-AUD-001 | `frontend/src/pages/Audit.test.tsx` |
| `/settings` | FE-UNIT-SET-001 | `frontend/src/pages/Settings.test.tsx` |
| `/profile` | FE-UNIT-PROF-001 | `frontend/src/pages/Profile.test.tsx` |
| Legacy redirects → `/audit` | FE-UNIT-REDIR-001 | `frontend/src/App.routes.test.tsx` |
| RequireAuth / CapabilityRoute | FE-UNIT-GUARD-001 | `frontend/src/auth/RequireAuth.test.tsx` |

---

## 8. Frontend auth / API / utils / forms

| Surface | Test ID | File |
|---------|---------|------|
| `permissions.ts` role matrix | FE-UNIT-PERM-001 | `frontend/src/auth/permissions.test.ts` |
| `sessionCapabilities.ts` | FE-UNIT-CAP-001 | `frontend/src/auth/sessionCapabilities.test.ts` |
| `AuthContext` | FE-UNIT-AUTH-CTX-001 | `frontend/src/auth/AuthContext.test.tsx` |
| `api.ts` login/refresh/401 | FE-UNIT-API-001 | `frontend/src/services/api.test.ts` |
| All `api.ts` endpoint wrappers | FE-UNIT-API-002 | same (MSW contract) |
| AddEmployeeModal dept/shift | FE-UNIT-EMP-FORM-001 | `frontend/src/components/employees/AddEmployeeModal.test.tsx` |
| OffboardEmployeeDialog | FE-UNIT-EMP-FORM-002 | `frontend/src/components/employees/OffboardEmployeeDialog.test.tsx` |
| AttendanceAdjustmentPanel | FE-UNIT-ADJ-001 | `frontend/src/components/attendance/AttendanceAdjustmentPanel.test.tsx` |
| AddAccountModal | FE-UNIT-ACCT-001 | `frontend/src/components/accounts/AddAccountModal.test.tsx` |
| ChangePasswordCard | FE-UNIT-PWD-001 | `frontend/src/components/settings/ChangePasswordCard.test.tsx` |
| Sidebar nav + sync | FE-UNIT-SIDE-001 | `frontend/src/components/layout/Sidebar.test.tsx` |
| TopBar + bell stub | FE-UNIT-TOPBAR-001 | `frontend/src/components/layout/TopBar.test.tsx` |
| reportExports excel | FE-UNIT-XLS-001 | `frontend/src/utils/reportExports/excel.test.ts` |
| reportExports pdf | FE-UNIT-PDF-001 | `frontend/src/utils/reportExports/pdf.test.ts` |
| reportExports word | FE-UNIT-DOCX-001 | `frontend/src/utils/reportExports/word.test.ts` |
| reportExports shared | FE-UNIT-EXP-SHARED-001 | `frontend/src/utils/reportExports/shared.test.ts` |
| dashboardAnalytics | FE-UNIT-ANALYT-001 | `frontend/src/lib/dashboardAnalytics.test.ts` |
| dates helpers | FE-UNIT-DATES-001 | `frontend/src/lib/dates.test.ts` |
| ui-store | FE-UNIT-STORE-001 | `frontend/src/stores/ui-store.test.ts` |

---

## 9. Playwright E2E

| Scenario | Test ID | File |
|----------|---------|------|
| Auth login/logout/forbidden | E2E-AUTH-001 | `e2e/scenarios/auth.spec.ts` |
| Employees CRUD + offboard | E2E-EMP-001 | `e2e/scenarios/employees.spec.ts` |
| Sync + attendance | E2E-ATT-001 | `e2e/scenarios/attendance_workflow.spec.ts` |
| Correction → audit | E2E-CORR-001 | `e2e/scenarios/correction_audit.spec.ts` |
| Report exports | E2E-EXP-001 | `e2e/scenarios/reports_export.spec.ts` |
| Operations queue | E2E-OPS-001 | `e2e/scenarios/operations.spec.ts` |
| Permissions matrix | E2E-PERM-001 | `e2e/scenarios/permissions_matrix.spec.ts` |
| Company day story | E2E-DAY-001 | `e2e/scenarios/company_day.spec.ts` |

---

## 10. Out of scope (no test IDs — not in product)

| Requested topic | Matrix status |
|-----------------|---------------|
| Holiday management | UNIMPLEMENTED |
| Leave management | UNIMPLEMENTED |
| Payroll calculations | UNIMPLEMENTED |
| Late arrival / early exit engines | UNIMPLEMENTED |
| Approval workflows | REMOVED (`0018`) |
| Notifications feed/API | UNIMPLEMENTED (bell stub → FE-UNIT-TOPBAR-001 documents absence of API) |
| AI correction suggestions | UNIMPLEMENTED |
| Vendor/ERP software sync | UNIMPLEMENTED |

---

## 11. Completeness gate

`scripts/check_traceability_matrix.py` verifies:

1. Every route discovered from FastAPI `app.routes` appears in §1.  
2. Every Celery task name in `app.workers.tasks` appears in §4.  
3. Every page under `frontend/src/pages/*.tsx` appears in §7.  
4. Every `testid` referenced in this matrix exists as a pytest marker or Playwright annotation in the suite (warn until implemented; fail in CI once harness lands).
