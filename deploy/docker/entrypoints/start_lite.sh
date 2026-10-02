#!/usr/bin/env sh
# 文件功能：在 SQLite 轻量单容器模式下执行迁移，并同时启动 Backend、Runtime 与 Nginx Gateway。

set -eu

backend_pid=""
runtime_pid=""
renderer_pid=""
nginx_pid=""

# 停止子进程并等待退出，避免容器收到终止信号时留下后台服务。
stop_services() {
    trap - INT TERM

    if [ -n "$nginx_pid" ] && kill -0 "$nginx_pid" 2>/dev/null; then
        nginx -s quit >/dev/null 2>&1 || true
    fi

    for pid in "$renderer_pid" "$runtime_pid" "$backend_pid" "$nginx_pid"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done

    for pid in "$nginx_pid" "$renderer_pid" "$runtime_pid" "$backend_pid"; do
        if [ -n "$pid" ]; then
            wait "$pid" 2>/dev/null || true
        fi
    done
}

# 为复用现有 Gateway 配置补齐单容器内 upstream 名称解析。
ensure_local_upstreams() {
    if ! grep -Eq '(^|[[:space:]])backend([[:space:]]|$)' /etc/hosts \
        || ! grep -Eq '(^|[[:space:]])runtime([[:space:]]|$)' /etc/hosts \
        || ! grep -Eq '(^|[[:space:]])renderer([[:space:]]|$)' /etc/hosts; then
        printf '\n127.0.0.1 backend runtime renderer\n' >> /etc/hosts
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
    : "${RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE:=runtime-diagnostics}"
    : "${RUNTIME_LOG_LEVEL:=info}"
    : "${RUNTIME_LOG_FORMAT:=json}"
    : "${RUNTIME_ACCESS_LOG_ENABLED:=false}"
    : "${RUNTIME_STANDALONE_PREVIEW_ENABLED:=false}"
    : "${ASSET_STORAGE_DRIVER:=local}"
    if [ -z "${RENDER_WORKERS_CONFIG:-}" ]; then
        RENDER_WORKERS_CONFIG='[{"worker_id":"renderer-lite","base_url":"http://127.0.0.1:7400"}]'
    fi
    : "${RENDER_WORKER_ID:=renderer-lite}"
    : "${RENDER_RUNTIME_NAVIGATION_BASE_URL:=http://127.0.0.1:7373}"
    : "${RENDER_RUNTIME_ASSET_BASE_URL:=http://127.0.0.1:7373}"
    : "${RENDER_PLATFORM_ASSET_BASE_URL:=http://127.0.0.1:8000}"
    : "${RENDER_PROFILE_DIGEST:=profile.v1}"
    : "${PLAYWRIGHT_BROWSERS_PATH:=/ms-playwright}"

    if [ -z "${RUNTIME_PUBLIC_BASE_URL:-}" ]; then
        RUNTIME_PUBLIC_BASE_URL="${BACKEND_PUBLIC_BASE_URL%/}/runtime"
    fi
    if [ -z "${CORS_ORIGINS:-}" ]; then
        CORS_ORIGINS='["http://127.0.0.1:8080"]'
    fi

    # CFG1(b): 单镜像内共享服务凭证，启动时自动生成强随机值并导出给同容器各子进程
    if [ -z "${RUNTIME_BUILD_WORKER_CREDENTIAL:-}" ] || [ "${RUNTIME_BUILD_WORKER_CREDENTIAL:-}" = "REPLACE_WITH_STRONG_BUILD_CREDENTIAL" ]; then
        RUNTIME_BUILD_WORKER_CREDENTIAL="$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)"
    fi
    if [ -z "${RENDER_SERVICE_CREDENTIAL:-}" ] || [ "${RENDER_SERVICE_CREDENTIAL:-}" = "REPLACE_WITH_STRONG_RENDER_CREDENTIAL" ] || [ "${RENDER_SERVICE_CREDENTIAL:-}" = "replace-with-strong-shared-secret" ]; then
        RENDER_SERVICE_CREDENTIAL="$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)"
    fi

    # CFG1(a): AI 对称加密密钥持久化自动生成落盘 /app/backend/data/ai_secret.key
    ai_key_file="/app/backend/data/ai_secret.key"
    if [ -z "${AI_SECRET_ENCRYPTION_KEY:-}" ] \
        || [ "${AI_SECRET_ENCRYPTION_KEY:-}" = "REPLACE_WITH_GENERATED_FERNET_KEY" ] \
        || [ "${AI_SECRET_ENCRYPTION_KEY:-}" = "vmgRweOsDpMtYVW7SSpceINYcXlUHFNndAby6vRv0iA=" ] \
        || [ "${AI_SECRET_ENCRYPTION_KEY:-}" = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" ]; then
        if [ -s "$ai_key_file" ]; then
            AI_SECRET_ENCRYPTION_KEY="$(cat "$ai_key_file" | tr -d '\r\n ')"
        else
            AI_SECRET_ENCRYPTION_KEY="$(/app/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
            printf '%s' "$AI_SECRET_ENCRYPTION_KEY" > "$ai_key_file"
            chmod 600 "$ai_key_file" 2>/dev/null || true
        fi
    fi

    # CFG1(c): 首启强随机管理员密码
    db_file="/app/backend/data/web_presentation.db"
    if [ ! -s "$db_file" ] && { [ -z "${DEFAULT_ADMIN_PASSWORD:-}" ] \
        || [ "${DEFAULT_ADMIN_PASSWORD:-}" = "REPLACE_WITH_STRONG_PASSWORD" ] \
        || [ "${DEFAULT_ADMIN_PASSWORD:-}" = "Admin123456" ]; }; then
        DEFAULT_ADMIN_PASSWORD="$(head -c 24 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 16)"
        printf '\n====================================================================\n'
        printf '[Lite 首启提示] 已为平台管理员账号 (admin) 自动生成初始随机密码：\n'
        printf '       %s\n' "$DEFAULT_ADMIN_PASSWORD"
        printf '请保存此密码，并在登录后尽快通过系统设置修改管理员口令。\n'
        printf '====================================================================\n\n'
    fi

    export DATABASE_URL REDIS_URL REDIS_KEY_PREFIX BACKEND_PUBLIC_BASE_URL RUNTIME_BASE_URL
    export RUNTIME_PUBLIC_BASE_URL RUNTIME_PREVIEW_JWKS_URL RUNTIME_BACKEND_API_BASE_URL
    export RUNTIME_SERVER_HOST RUNTIME_SERVER_PORT RUNTIME_SERVER_BASE_PATH
    export RUNTIME_SERVICE_TOKEN_AUDIENCE RUNTIME_PREVIEW_TOKEN_AUDIENCE
    export RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE
    export RUNTIME_LOG_LEVEL RUNTIME_LOG_FORMAT RUNTIME_ACCESS_LOG_ENABLED
    export RUNTIME_STANDALONE_PREVIEW_ENABLED ASSET_STORAGE_DRIVER CORS_ORIGINS
    export RENDER_WORKERS_CONFIG RENDER_WORKER_ID RENDER_RUNTIME_NAVIGATION_BASE_URL
    export RENDER_RUNTIME_ASSET_BASE_URL RENDER_PLATFORM_ASSET_BASE_URL RENDER_PROFILE_DIGEST
    export PLAYWRIGHT_BROWSERS_PATH
    export RUNTIME_BUILD_WORKER_CREDENTIAL RENDER_SERVICE_CREDENTIAL
    export AI_SECRET_ENCRYPTION_KEY
    if [ -n "${DEFAULT_ADMIN_PASSWORD:-}" ]; then
        export DEFAULT_ADMIN_PASSWORD
    fi
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

/app/.venv-renderer/bin/uvicorn wp_renderer.main:app \
    --host 127.0.0.1 \
    --port 7400 \
    --no-access-log &
renderer_pid="$!"

nginx -g "daemon off;" &
nginx_pid="$!"

exit_status=0

while kill -0 "$backend_pid" 2>/dev/null \
    && kill -0 "$runtime_pid" 2>/dev/null \
    && kill -0 "$nginx_pid" 2>/dev/null \
    && kill -0 "$renderer_pid" 2>/dev/null; do
    sleep 2
done

for pid in "$backend_pid" "$runtime_pid" "$nginx_pid" "$renderer_pid"; do
    if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" || exit_status="$?"
    fi
done

stop_services
exit "$exit_status"
