#!/bin/sh
# 文件功能：导出 PostgreSQL 业务库备份，并写入版本/校验和清单，支撑 AR-06/W06 与 M07。

set -eu
umask 077

# 可覆盖配置：与部署环境对齐，不要把生产凭据写入仓库。
# 备份输出目录（会创建 <BACKUP_ROOT>/<TIMESTAMP>/）。
BACKUP_ROOT=${BACKUP_ROOT:-/var/backups/web-presentation}
# Compose 文件；用于在内置 postgres 服务上执行 pg_dump。留空则使用本机 pg_dump。
COMPOSE_FILE=${COMPOSE_FILE:-}
# 使用 compose 时的 postgres 服务名。
COMPOSE_SERVICE=${COMPOSE_SERVICE:-postgres}
# 直连时的 PostgreSQL 连接参数（优先使用 PGPASSWORD / .pgpass，不要把密码写进命令行历史）。
PGHOST=${PGHOST:-}
PGPORT=${PGPORT:-5432}
PGUSER=${PGUSER:-wp_user}
PGDATABASE=${PGDATABASE:-web_presentation}
# 备份与恢复共用锁。
LOCK_DIR=${LOCK_DIR:-/tmp/web-presentation-pg-backup.lock}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST_DIR="$BACKUP_ROOT/$TIMESTAMP"
LOCK_ACQUIRED=0

log() {
  printf '%s %s\n' '[pg-backup]' "$*"
}

fail() {
  log "错误：$*" >&2
  exit 1
}

cleanup() {
  if [ "$LOCK_ACQUIRED" -eq 1 ]; then
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_ACQUIRED=1
    return 0
  fi
  fail "无法获取锁 $LOCK_DIR，可能已有备份/恢复任务在运行"
}

# 在 compose 的 postgres 服务上执行 pg_dump，或回落本机 pg_dump。
run_pg_dump() {
  output_file=$1
  if [ -n "$COMPOSE_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T "$COMPOSE_SERVICE" \
      pg_dump -U "$PGUSER" -d "$PGDATABASE" -Fc >"$output_file"
  else
    [ -n "$PGHOST" ] || fail "未设置 COMPOSE_FILE 或 PGHOST，无法定位 PostgreSQL"
    pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc >"$output_file"
  fi
}

# 读取当前 alembic 版本，写入清单便于恢复时核对镜像兼容性。
capture_alembic_version() {
  output_file=$1
  if [ -n "$COMPOSE_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T "$COMPOSE_SERVICE" \
      psql -U "$PGUSER" -d "$PGDATABASE" -tAc "select version_num from alembic_version;" \
      >"$output_file" 2>/dev/null || echo "unknown" >"$output_file"
  else
    PGPASSWORD="${PGPASSWORD:-}" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
      -tAc "select version_num from alembic_version;" >"$output_file" 2>/dev/null \
      || echo "unknown" >"$output_file"
  fi
}

acquire_lock
mkdir -p "$DEST_DIR"
log "备份输出目录：$DEST_DIR"

DUMP_FILE="$DEST_DIR/web_presentation.dump"
run_pg_dump "$DUMP_FILE"
[ -s "$DUMP_FILE" ] || fail "pg_dump 未产生有效输出"

# 校验和：Linux 用 sha256sum，macOS 用 shasum。
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$DEST_DIR" && sha256sum web_presentation.dump >SHA256SUMS)
elif command -v shasum >/dev/null 2>&1; then
  (cd "$DEST_DIR" && shasum -a 256 web_presentation.dump >SHA256SUMS)
else
  log "警告：系统无 sha256sum/shasum，跳过校验和"
fi

capture_alembic_version "$DEST_DIR/alembic_version.txt"

cat >"$DEST_DIR/manifest.txt" <<EOF
backup_type=postgresql
created_at_utc=$TIMESTAMP
pg_database=$PGDATABASE
pg_user=$PGUSER
alembic_version=$(cat "$DEST_DIR/alembic_version.txt")
dump_file=web_presentation.dump
# 恢复时还必须同步：backend-data（local 资源/截图/构建产物）、
# AI_SECRET_ENCRYPTION_KEY、RUNTIME_RSA_*、RENDER/BUILD 凭证、S3 凭证（若使用）。
# 完整清单见 docs/deployment/operations/backup-restore.md
EOF

log "完成：$DEST_DIR"
log "请一并归档 backend-data volume 与密钥，并记录镜像 digest。"
