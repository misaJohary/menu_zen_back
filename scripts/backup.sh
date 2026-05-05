#!/bin/sh
set -eu

# Loaded from the project's .env (same vars as compose)
PROJECT_DIR="${PROJECT_DIR:-/opt/menu_zen_back}"
cd "$PROJECT_DIR"
. ./.env

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMPFILE="/tmp/menuzen_${STAMP}.sql.gz"
S3_KEY="postgres/menuzen_${STAMP}.sql.gz"

# 1. Dump from the running container (no host-side psql/pg_dump needed)
docker compose -f docker-compose.yml exec -T db \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --clean \
    | gzip -9 > "${TMPFILE}"

# 2. Upload via aws-cli (configured to point at OVH's S3-compatible endpoint)
AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
aws --endpoint-url "${BACKUP_S3_ENDPOINT}" \
    s3 cp "${TMPFILE}" "${BACKUP_S3_BUCKET}/${S3_KEY}"

# 3. Cleanup local tmp
rm -f "${TMPFILE}"

# 4. Prune remote dumps older than retention window
CUTOFF=$(date -u -d "-${BACKUP_RETENTION_DAYS} days" +%Y-%m-%d 2>/dev/null \
       || date -u -v-"${BACKUP_RETENTION_DAYS}"d +%Y-%m-%d)
AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
aws --endpoint-url "${BACKUP_S3_ENDPOINT}" \
    s3 ls "${BACKUP_S3_BUCKET}/postgres/" \
    | awk -v cutoff="${CUTOFF}" '$1 < cutoff {print $4}' \
    | while read -r OLD; do
        [ -n "${OLD}" ] && AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
            AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
            aws --endpoint-url "${BACKUP_S3_ENDPOINT}" \
            s3 rm "${BACKUP_S3_BUCKET}/postgres/${OLD}"
      done

echo "Backup ${S3_KEY} uploaded."
