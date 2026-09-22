# 文件功能：构建独立 Renderer 长期镜像；Backend 镜像不再安装浏览器。

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

LABEL org.opencontainers.image.title="web-presentation-renderer"
LABEL org.opencontainers.image.description="Remote render execution service"

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
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
COPY renderer/app /app/renderer/app

RUN uv sync --package web-presentation-renderer --frozen --no-dev --no-cache \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/renderer

RUN python -c "import render_contracts, app.main"

EXPOSE 7400

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7400"]
