#!/usr/bin/env bash
# Backup PostgreSQL for the biometric platform.
# Usage:
#   ./scripts/backup_pg.sh
#   DATABASE_URL=postgresql://user:pass@host:5432/db ./scripts/backup_pg.sh /path/to/backups
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_DIR}"

if [[ -n "${DATABASE_URL:-}" ]]; then
  # Strip SQLAlchemy driver suffix if present (postgresql+psycopg:// → postgresql://)
  PG_URL="${DATABASE_URL/+psycopg/}"
  PG_URL="${PG_URL/+psycopg2/}"
else
  PGHOST="${DB_HOST:-localhost}"
  PGPORT="${DB_PORT:-5432}"
  PGUSER="${DB_USER:-biometric}"
  PGPASSWORD="${DB_PASSWORD:-biometric}"
  PGDATABASE="${DB_NAME:-biometric}"
  export PGPASSWORD
  PG_URL="postgresql://${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
fi

OUT_FILE="${BACKUP_DIR}/biometric_${TIMESTAMP}.dump"
echo "Backing up to ${OUT_FILE}"
pg_dump --format=custom --file="${OUT_FILE}" "${PG_URL}"
# Write sidecar checksum for restore_verify.sh
sha256sum "${OUT_FILE}" > "${OUT_FILE}.sha256"
echo "Backup complete: ${OUT_FILE}"
ls -lh "${OUT_FILE}"
