#!/bin/sh
# 文件功能：从 pg-backup 产物恢复 PostgreSQL，并支持隔离演练目标，支撑 AR-06/W06 与 M07。

set -eu
umask 077

# 可覆盖配置。
# 备份目录（含 web_presentation.dump 与 manifest.txt）。
BACKUP_DIR=${BACKUP_DIR:-}
# Compose 文件；用于在内置 postgres 上恢复。留空则使用本机 psql/pg_restore。
COMPOSE_FILE=${COMPOSE_FILE:-}
COMPOSE_SERVICE=${COMPOSE_SERVICE:-postgres}
PGHOST=${PGHOST:-}
PGPORT=${PGPORT:-5432}
PGUSER=${PGUSER:-wp_user}
PGDATABASE=${PGDATABASE:-web_presentation}
# 隔离演练：目标数据库名（默认与源库相同）。隔离恢复必须使用独立库/实例，禁止指向生产。
RESTORE_DATABASE=${RESTORE_DATABASE:-$PGDATABASE}
# 是否在恢复前强制结束其它连接（隔离演练目标库可开；生产慎用）。
FORCE_DROP=${FORCE_DROP:-false}
LOCK_DIR=${LOCK_DIR:-/tmp/web-presentation-pg-restore.lock}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LOCK_ACQUIRED=0

log() {
  printf '%s %s\n' '[pg-restore]' "$*"
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

[ -n "$BACKUP_DIR" ] || fail "必须设置 BACKUP_DIR"
[ -d "$BACKUP_DIR" ] || fail "BACKUP_DIR 不存在：$BACKUP_DIR"
DUMP_FILE="$BACKUP_DIR/web_presentation.dump"
[ -s "$DUMP_FILE" ] || fail "缺少备份文件：$DUMP_FILE"

if [ -f "$BACKUP_DIR/SHA256SUMS" ]; then
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS) || fail "备份校验和不匹配，拒绝恢复"
    log "校验和通过"
  else
    log "警告：无法校验 SHA256SUMS（本机无 sha256sum）"
  fi
fi

if [ -f "$BACKUP_DIR/alembic_version.txt" ]; then
  log "备份时 alembic_version=$(cat "$BACKUP_DIR/alembic_version.txt")"
  log "请确认目标镜像包含该 revision；不匹配会在启动时报 Can't locate revision"
fi

acquire_lock

run_psql() {
  if [ -n "$COMPOSE_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T "$COMPOSE_SERVICE" psql -U "$PGUSER" "$@"
  else
    [ -n "$PGHOST" ] || fail "未设置 COMPOSE_FILE 或 PGHOST"
    PGPASSWORD="${PGPASSWORD:-}" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" "$@"
  fi
}

run_pg_restore() {
  if [ -n "$COMPOSE_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T "$COMPOSE_SERVICE" \
      pg_restore -U "$PGUSER" -d "$RESTORE_DATABASE" --clean --if-exists <"$DUMP_FILE"
  else
    [ -n "$PGHOST" ] || fail "未设置 COMPOSE_FILE 或 PGHOST"
    PGPASSWORD="${PGPASSWORD:-}" pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" \
      -d "$RESTORE_DATABASE" --clean --if-exists <"$DUMP_FILE"
  fi
}

if [ "$FORCE_DROP" = "true" ]; then
  log "强制结束 $RESTORE_DATABASE 上的其它连接（FORCE_DROP=true）"
  run_psql -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$RESTORE_DATABASE' AND pid<>pg_backend_pid();" \
    >/dev/null
fi

log "恢复到数据库：$RESTORE_DATABASE"
run_pg_restore
log "恢复完成。请按 backup-restore.md 验证：登录、读页、资源、AI 凭据解密、预览/截图/构建。"
log "隔离演练请确认目标不是生产实例（COMPOSE_FILE / PGHOST / RESTORE_DATABASE）。"
