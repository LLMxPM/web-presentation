# 文件功能：构建独立 Renderer 长期镜像；Backend 镜像不再安装浏览器。

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

LABEL org.opencontainers.image.title="web-presentation-renderer"
LABEL org.opencontainers.image.description="Remote render execution service"

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/app/renderer/.venv/bin:${PATH}" \
    VIRTUAL_ENV="/app/renderer/.venv"

# 保持与源码树一致的相对布局：
#   /app/packages/render-contracts  ←  pyproject 中 ../packages/render-contracts
#   /app/renderer/{pyproject.toml,app}
WORKDIR /app

COPY packages/render-contracts /app/packages/render-contracts
COPY renderer/pyproject.toml renderer/uv.lock /app/renderer/
COPY renderer/app /app/renderer/app

WORKDIR /app/renderer

RUN uv sync --frozen --no-dev --no-cache \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && python -c "import render_contracts, app.main"

EXPOSE 7400

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7400"]
