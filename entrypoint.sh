#!/usr/bin/env sh
set -e

alembic upgrade head
python -c "from app.core.database import create_tables; create_tables()"
exec "$@"
