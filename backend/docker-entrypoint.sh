#!/bin/sh
set -e
if [ -z "$SKIP_MIGRATIONS" ]; then
  alembic upgrade head
fi
exec "$@"
