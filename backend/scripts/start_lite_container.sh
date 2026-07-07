#!/usr/bin/env sh
# 文件功能：在 SQLite 轻量单容器模式下执行迁移，并同时启动 Backend、Runtime 与 Nginx Gateway。

set -eu

backend_pid=""
runtime_pid=""
nginx_pid=""

# 停止子进程并等待退出，避免容器收到终止信号时留下后台服务。
stop_services() {
    trap - INT TERM

    if [ -n "$nginx_pid" ] && kill -0 "$nginx_pid" 2>/dev/null; then
        nginx -s quit >/dev/null 2>&1 || true
    fi

    for pid in "$runtime_pid" "$backend_pid" "$nginx_pid"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done

    for pid in "$nginx_pid" "$runtime_pid" "$backend_pid"; do
        if [ -n "$pid" ]; then
            wait "$pid" 2>/dev/null || true
        fi
    done
}

# 为复用现有 Gateway 配置补齐单容器内 upstream 名称解析。
ensure_local_upstreams() {
    if ! grep -Eq '(^|[[:space:]])backend([[:space:]]|$)' /etc/hosts \
        || ! grep -Eq '(^|[[:space:]])runtime([[:space:]]|$)' /etc/hosts; then
        printf '\n127.0.0.1 backend runtime\n' >> /etc/hosts
    fi
}

# 设置轻量部署默认环境变量；用户传入的环境变量优先。
configure_lite_defaults() {
    : "${DATABASE_URL:=sqlite+aiosqlite:////app/backend/data/web_presentation.db}"
    : "${REDIS_URL:=memory://lite}"
    : "${REDIS_KEY_PREFIX:=web_presentation_lite}"
    : "${BACKEND_PUBLIC_BASE_URL:=http://127.0.0.1:8080}"
    : "${RUNTIME_BASE_URL:=http://127.0.0.1:7373}"
    : "${RUNTIME_PREVIEW_JWKS_URL:=http://127.0.0.1:8000/.well-known/jwks.json}"
    : "${RUNTIME_BACKEND_API_BASE_URL:=http://127.0.0.1:8000}"
    : "${RUNTIME_SERVER_HOST:=0.0.0.0}"
    : "${RUNTIME_SERVER_PORT:=7373}"
    : "${RUNTIME_SERVER_BASE_PATH:=/runtime/}"
    : "${RUNTIME_SERVICE_TOKEN_AUDIENCE:=runtime-backend}"
    : "${RUNTIME_PREVIEW_TOKEN_AUDIENCE:=runtime-preview}"
    : "${RUNTIME_BUILD_TOKEN_AUDIENCE:=runtime-build}"
    : "${RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE:=runtime-diagnostics}"
    : "${RUNTIME_LOG_LEVEL:=info}"
    : "${RUNTIME_LOG_FORMAT:=json}"
    : "${RUNTIME_ACCESS_LOG_ENABLED:=true}"
    : "${RUNTIME_STANDALONE_PREVIEW_ENABLED:=false}"
    : "${ASSET_STORAGE_DRIVER:=local}"

    if [ -z "${RUNTIME_PUBLIC_BASE_URL:-}" ]; then
        RUNTIME_PUBLIC_BASE_URL="${BACKEND_PUBLIC_BASE_URL%/}/runtime"
    fi
    if [ -z "${CORS_ORIGINS:-}" ]; then
        CORS_ORIGINS='["http://127.0.0.1:8080"]'
    fi

    export DATABASE_URL REDIS_URL REDIS_KEY_PREFIX BACKEND_PUBLIC_BASE_URL RUNTIME_BASE_URL
    export RUNTIME_PUBLIC_BASE_URL RUNTIME_PREVIEW_JWKS_URL RUNTIME_BACKEND_API_BASE_URL
    export RUNTIME_SERVER_HOST RUNTIME_SERVER_PORT RUNTIME_SERVER_BASE_PATH
    export RUNTIME_SERVICE_TOKEN_AUDIENCE RUNTIME_PREVIEW_TOKEN_AUDIENCE
    export RUNTIME_BUILD_TOKEN_AUDIENCE RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE
    export RUNTIME_LOG_LEVEL RUNTIME_LOG_FORMAT RUNTIME_ACCESS_LOG_ENABLED
    export RUNTIME_STANDALONE_PREVIEW_ENABLED ASSET_STORAGE_DRIVER CORS_ORIGINS
}

trap stop_services INT TERM

configure_lite_defaults
ensure_local_upstreams
mkdir -p /app/backend/data

if [ "${PLATFORM_LITE_RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic upgrade head
fi

uvicorn app.main:app \
    --host "${BACKEND_HOST:-0.0.0.0}" \
    --port "${BACKEND_PORT:-8000}" \
    --no-access-log &
backend_pid="$!"

(
    cd /app/runtime
    exec node node_modules/vite/bin/vite.js
) &
runtime_pid="$!"

nginx -g "daemon off;" &
nginx_pid="$!"

exit_status=0

while kill -0 "$backend_pid" 2>/dev/null \
    && kill -0 "$runtime_pid" 2>/dev/null \
    && kill -0 "$nginx_pid" 2>/dev/null; do
    sleep 2
done

for pid in "$backend_pid" "$runtime_pid" "$nginx_pid"; do
    if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" || exit_status="$?"
    fi
done

stop_services
exit "$exit_status"
