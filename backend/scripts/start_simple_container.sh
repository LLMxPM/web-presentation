#!/usr/bin/env sh
# 文件功能：在 simple 容器部署模式下执行数据库迁移，并同时启动 Backend 与 Nginx Gateway。

set -eu

backend_pid=""
nginx_pid=""

# 停止子进程并等待退出，避免容器收到终止信号时留下后台服务。
stop_services() {
    trap - INT TERM

    if [ -n "$nginx_pid" ] && kill -0 "$nginx_pid" 2>/dev/null; then
        nginx -s quit >/dev/null 2>&1 || kill "$nginx_pid" 2>/dev/null || true
    fi

    if [ -n "$backend_pid" ] && kill -0 "$backend_pid" 2>/dev/null; then
        kill "$backend_pid" 2>/dev/null || true
    fi

    wait "$nginx_pid" "$backend_pid" 2>/dev/null || true
}

trap stop_services INT TERM

if [ "${PLATFORM_SIMPLE_RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic upgrade head
fi

uvicorn app.main:app \
    --host "${BACKEND_HOST:-0.0.0.0}" \
    --port "${BACKEND_PORT:-8000}" \
    --no-access-log &
backend_pid="$!"

nginx -g "daemon off;" &
nginx_pid="$!"

exit_status=0

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
    sleep 2
done

if ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid" || exit_status="$?"
fi

if ! kill -0 "$nginx_pid" 2>/dev/null; then
    wait "$nginx_pid" || exit_status="$?"
fi

stop_services
exit "$exit_status"
