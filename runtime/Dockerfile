# 文件功能：构建独立 Runtime 长期镜像；Backend 镜像不再安装浏览器。
# 构建上下文为仓库根目录（pnpm workspace 共享 pnpm-lock.yaml）。

FROM node:22-bookworm-slim

LABEL org.opencontainers.image.title="web-runtime-vue"
LABEL org.opencontainers.image.description="web-presentation Runtime Vite server image"

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"
ENV RUNTIME_SERVER_HOST=0.0.0.0
ENV RUNTIME_SERVER_PORT=7373
ENV RUNTIME_LOG_LEVEL=info
ENV RUNTIME_LOG_FORMAT=json
ENV RUNTIME_ACCESS_LOG_ENABLED=true
ENV RUNTIME_STANDALONE_PREVIEW_ENABLED=false

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10.30.3 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY editor/package.json ./editor/
COPY runtime/package.json ./runtime/
RUN pnpm install --frozen-lockfile --filter web-runtime-vue...

COPY runtime/ ./runtime/
# deploy 产出可独立拷贝的 node_modules，避免 workspace 符号链接失效
RUN pnpm --filter web-runtime-vue deploy --legacy --prod /app/runtime-dist \
    && mv /app/runtime-dist /opt/runtime \
    && rm -rf /app/runtime /app/editor /app/node_modules /app/package.json /app/pnpm-lock.yaml /app/pnpm-workspace.yaml

WORKDIR /opt/runtime

EXPOSE 7373

HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD node -e "const port=process.env.RUNTIME_SERVER_PORT||'7373'; fetch('http://127.0.0.1:'+port+'/__runtime_healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "node_modules/vite/bin/vite.js"]
