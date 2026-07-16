#!/usr/bin/env bash
# Verify a pg_dump custom-format backup and optionally restore into a scratch DB.
# Usage:
#   ./scripts/restore_verify.sh ./backups/biometric_YYYYMMDD.dump
#   VERIFY_RESTORE=1 ./scripts/restore_verify.sh ./backups/biometric_YYYYMMDD.dump
set -euo pipefail

DUMP_FILE="${1:-}"
if [[ -z "${DUMP_FILE}" || ! -f "${DUMP_FILE}" ]]; then
  echo "Usage: $0 <path-to-pg_dump-custom-file>" >&2
  exit 1
fi

echo "Verifying dump listing: ${DUMP_FILE}"
pg_restore --list "${DUMP_FILE}" >/dev/null
echo "Dump TOC readable OK"

if [[ -f "${DUMP_FILE}.sha256" ]]; then
  echo "Checking SHA-256 sidecar..."
  sha256sum -c "${DUMP_FILE}.sha256"
fi

if [[ "${VERIFY_RESTORE:-0}" != "1" ]]; then
  echo "Set VERIFY_RESTORE=1 to perform a scratch restore (requires scratch DB)."
  exit 0
fi

SCRATCH_DB="${SCRATCH_DB:-biometric_restore_verify}"
PGHOST="${DB_HOST:-localhost}"
PGPORT="${DB_PORT:-5432}"
PGUSER="${DB_USER:-biometric}"
export PGPASSWORD="${DB_PASSWORD:-biometric}"

echo "Creating scratch database ${SCRATCH_DB}"
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${SCRATCH_DB};" \
  -c "CREATE DATABASE ${SCRATCH_DB};"

echo "Restoring into ${SCRATCH_DB}"
pg_restore --clean --if-exists --no-owner --dbname="postgresql://${PGUSER}@${PGHOST}:${PGPORT}/${SCRATCH_DB}" "${DUMP_FILE}"

TABLE_COUNT="$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${SCRATCH_DB}" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
echo "Scratch restore OK — public tables: ${TABLE_COUNT}"

if [[ "${KEEP_SCRATCH:-0}" != "1" ]]; then
  psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres \
    -c "DROP DATABASE IF EXISTS ${SCRATCH_DB};"
  echo "Scratch database dropped."
fi
