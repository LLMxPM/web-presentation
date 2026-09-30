# 文件功能：构建独立 Renderer 长期镜像；Backend 镜像不再安装浏览器。

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

LABEL org.opencontainers.image.title="web-presentation-renderer"
LABEL org.opencontainers.image.description="Remote render execution service"

# 允许构建时覆盖 Python 包索引、Debian 源与 Playwright 浏览器下载源。
ARG UV_INDEX_URL=https://pypi.org/simple
ARG DEBIAN_MIRROR=
ARG PLAYWRIGHT_DOWNLOAD_HOST=

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_INDEX_URL=${UV_INDEX_URL} \
    UV_DEFAULT_INDEX=${UV_INDEX_URL} \
    UV_HTTP_TIMEOUT=180 \
    PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/app/.venv/bin:${PATH}" \
    VIRTUAL_ENV="/app/.venv"

# uv workspace 布局：根锁 + 全部成员元数据；可执行入口在 /app/renderer
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/
COPY renderer/pyproject.toml ./renderer/
COPY packages/render-contracts /app/packages/render-contracts
COPY renderer/wp_renderer /app/renderer/wp_renderer

RUN uv sync --package web-presentation-renderer --frozen --no-dev

# 默认 Debian 源使用 HTTPS，避免代理环境只允许 TLS 时大包下载不断超时；
# Python 同步独立成层，浏览器/系统依赖重试不需要重新下载整套 Python 包。
RUN set -eux; \
    find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -print0 \
      | xargs -0 -r sed -i 's|http://deb.debian.org|https://deb.debian.org|g'; \
    if [ -n "${DEBIAN_MIRROR}" ]; then \
      find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -print0 \
        | xargs -0 -r sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g"; \
    fi; \
    playwright install --with-deps chromium \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/renderer

RUN python -c "import render_contracts, wp_renderer"

EXPOSE 7400

CMD ["uvicorn", "wp_renderer.main:app", "--host", "0.0.0.0", "--port", "7400"]
