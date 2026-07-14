# syntax=docker/dockerfile:1.7
# 文件功能：构建 web-presentation 平台单镜像，镜像内同时包含 Backend 服务与 Editor 静态资源。

FROM node:22-bookworm-slim AS editor-build

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"

WORKDIR /app/editor

RUN corepack enable && corepack prepare pnpm@10.30.3 --activate

COPY editor/package.json editor/pnpm-lock.yaml editor/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY editor/ ./
RUN pnpm build


FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend-deps

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./backend/
RUN uv sync --project backend --frozen --no-dev --no-cache --no-install-project


FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS platform-runtime

LABEL org.opencontainers.image.title="web-presentation"
LABEL org.opencontainers.image.description="web-presentation Backend and Editor platform image"

ENV APP_RELOAD=false
ENV ACCESS_LOG_ENABLED=false
ENV PATH="/app/backend/.venv/bin:${PATH}"
ENV PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV="/app/backend/.venv"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nginx \
    && rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-available/default \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY --from=backend-deps /app/backend/.venv /app/backend/.venv
RUN playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ /app/backend/
COPY runtime/src/runtime-kit/manifest/runtime-kit.manifest.json /app/runtime/src/runtime-kit/manifest/runtime-kit.manifest.json
COPY --from=editor-build /app/editor/dist/ /usr/share/nginx/html/
COPY docker/nginx/web-presentation.conf /etc/nginx/conf.d/default.conf

RUN mkdir -p /app/backend/data /run/nginx /var/cache/nginx /var/log/nginx \
    && chmod +x /app/backend/scripts/start_simple_container.sh

EXPOSE 80 8000

CMD ["sh", "/app/backend/scripts/start_simple_container.sh"]
