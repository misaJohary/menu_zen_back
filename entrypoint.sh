#!/bin/sh
set -e

# Detect whether alembic has ever run against this database. If not,
# the existing migration chain assumes tables already exist (the schema
# was historically created by SQLModel.metadata.create_all() at app
# startup), so we bootstrap with create_all + stamp head. On every
# subsequent boot we just run `upgrade head` to apply new migrations.
INITIALIZED=$(python - <<'PY'
import os, sys
from sqlalchemy import create_engine, inspect
try:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        names = inspect(conn).get_table_names()
    print("yes" if "alembic_version" in names else "no")
except Exception as exc:
    sys.stderr.write(f"DB inspect failed: {exc}\n")
    print("no")
PY
)

if [ "$INITIALIZED" = "no" ]; then
    echo "Fresh database detected — creating schema and stamping alembic at head."
    python -c "from app.configs.database_configs import create_db_and_tables; create_db_and_tables()"
    alembic stamp head
else
    echo "Running database migrations..."
    alembic upgrade head
fi

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
