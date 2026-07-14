#!/bin/sh
# 文件功能：停止 SQLite 轻量 Demo 服务，并把完整 lite-data volume 备份为基线归档。

set -eu
umask 077

# 部署配置：可直接修改默认值，也可通过同名环境变量覆盖。
# 完整 lite-data volume 的备份归档路径。
BACKUP_FILE=${BACKUP_FILE:-/opt/presentation/lite-data.tar.gz}
# SQLite 轻量部署在 compose 中的服务名称。
COMPOSE_SERVICE=${COMPOSE_SERVICE:-platform-lite}
# lite-data volume 在应用容器内的挂载路径。
DATA_MOUNT_PATH=${DATA_MOUNT_PATH:-/app/backend/data}
# 备份与恢复任务共用的宿主机互斥锁目录。
LOCK_DIR=${LOCK_DIR:-/tmp/web-presentation-sqlite-demo-data.lock}
# 服务重新启动后等待健康检查通过的最长秒数。
HEALTH_TIMEOUT_SECONDS=${HEALTH_TIMEOUT_SECONDS:-120}
# Compose 文件路径；留空时自动使用脚本上级目录中的 SQLite 模板。
COMPOSE_FILE=${COMPOSE_FILE:-}

# 内部运行时变量。
# 当前脚本所在目录，用于推导默认 Compose 文件路径。
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -z "$COMPOSE_FILE" ]; then
  COMPOSE_FILE=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)/docker-compose.sqlite.yml
fi
# 标记服务是否已由本脚本停止，异常退出时据此自动拉起服务。
SERVICE_STOPPED=0
# 标记当前进程是否持有互斥锁，退出时据此清理锁目录。
LOCK_ACQUIRED=0

# 输出带统一前缀的运行日志，方便 cron 或 systemd 收集。
log() {
  printf '%s %s\n' '[sqlite-demo-backup]' "$*"
}

# 输出错误并终止脚本。
fail() {
  log "错误：$*" >&2
  exit 1
}

# 在固定 compose 文件上执行命令，避免工作目录变化影响运行。
compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

# 获取已有服务容器，备份前必须先完成 SQLite 部署。
get_container_id() {
  container_id=$(compose ps -aq "$COMPOSE_SERVICE")
  [ -n "$container_id" ] || fail "服务 $COMPOSE_SERVICE 尚未创建，请先启动 SQLite 部署"
  printf '%s\n' "$container_id"
}

# 从容器挂载信息解析实际 Docker volume 名称。
get_volume_name() {
  container_id=$1
  volume_name=$(docker inspect --format "{{range .Mounts}}{{if eq .Destination \"$DATA_MOUNT_PATH\"}}{{.Name}}{{end}}{{end}}" "$container_id")
  [ -n "$volume_name" ] || fail "容器未在 $DATA_MOUNT_PATH 挂载命名 volume"
  printf '%s\n' "$volume_name"
}

# 限制归档文件名，避免把环境变量内容拼入容器内 shell 命令。
validate_backup_name() {
  case "$1" in
    '' | *[!A-Za-z0-9._-]*) fail "BACKUP_FILE 文件名只能包含字母、数字、点、下划线和连字符" ;;
  esac
}

# 释放互斥锁；备份失败时优先恢复服务可用性。
cleanup() {
  exit_code=$1
  trap - 0 1 2 15
  if [ "$SERVICE_STOPPED" -eq 1 ]; then
    log "尝试重新启动 $COMPOSE_SERVICE"
    compose up -d "$COMPOSE_SERVICE" >/dev/null 2>&1 || true
  fi
  if [ "$LOCK_ACQUIRED" -eq 1 ]; then
    rm -f "$LOCK_DIR/pid"
    rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}

# 获取备份与恢复共用的互斥锁，并回收进程已退出的陈旧锁。
acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  old_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
  case "$old_pid" in
    '' | *[!0-9]*) ;;
    *) kill -0 "$old_pid" 2>/dev/null && fail "已有备份或恢复任务运行中，进程 ID：$old_pid" ;;
  esac
  rm -f "$LOCK_DIR/pid" 2>/dev/null || true
  if rmdir "$LOCK_DIR" 2>/dev/null && mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  fail "无法获取任务锁：$LOCK_DIR"
}

# 等待服务健康检查通过，超时返回失败以便定时任务告警。
wait_for_health() {
  elapsed=0
  while [ "$elapsed" -lt "$HEALTH_TIMEOUT_SECONDS" ]; do
    container_id=$(compose ps -q "$COMPOSE_SERVICE")
    if [ -n "$container_id" ]; then
      status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
      if [ "$status" = 'healthy' ] || [ "$status" = 'running' ]; then
        log "服务状态正常：$status"
        return 0
      fi
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  fail "服务在 ${HEALTH_TIMEOUT_SECONDS}s 内未恢复健康"
}

command -v docker >/dev/null 2>&1 || fail "缺少命令：docker"
[ -f "$COMPOSE_FILE" ] || fail "compose 文件不存在：$COMPOSE_FILE"
case "$HEALTH_TIMEOUT_SECONDS" in
  '' | *[!0-9]* | 0) fail "HEALTH_TIMEOUT_SECONDS 必须是正整数" ;;
esac

acquire_lock
LOCK_ACQUIRED=1
trap 'cleanup $?' 0
trap 'cleanup 130' 1 2
trap 'cleanup 143' 15

container_id=$(get_container_id)
volume_name=$(get_volume_name "$container_id")
image_name=$(docker inspect --format '{{.Config.Image}}' "$container_id")
backup_dir=$(dirname -- "$BACKUP_FILE")
backup_name=$(basename -- "$BACKUP_FILE")
validate_backup_name "$backup_name"

mkdir -p "$backup_dir"
log "停止 $COMPOSE_SERVICE 并创建基线：$BACKUP_FILE"
compose stop "$COMPOSE_SERVICE" >/dev/null
SERVICE_STOPPED=1

rm -f "$BACKUP_FILE.tmp"
docker run --rm --entrypoint sh \
  -v "$volume_name:/data:ro" \
  -v "$backup_dir:/backup" \
  "$image_name" \
  -c "tar -C /data -czf /backup/$backup_name.tmp ."
mv "$BACKUP_FILE.tmp" "$BACKUP_FILE"

compose up -d "$COMPOSE_SERVICE" >/dev/null
SERVICE_STOPPED=0
wait_for_health
log "基线创建完成：$BACKUP_FILE"
