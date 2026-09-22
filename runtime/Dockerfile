# syntax=docker/dockerfile:1.7
# 文件功能：构建 web-runtime-vue 平台运行时镜像，保留 Vite dev server 以承载预览、诊断与构建接口。

FROM node:22-bookworm-slim

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"
ENV RUNTIME_SERVER_HOST=0.0.0.0
ENV RUNTIME_SERVER_PORT=7373
ENV RUNTIME_LOG_LEVEL=info
ENV RUNTIME_LOG_FORMAT=json
ENV RUNTIME_ACCESS_LOG_ENABLED=true
ENV RUNTIME_STANDALONE_PREVIEW_ENABLED=false

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10.0.0 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 7373

HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD node -e "const port=process.env.RUNTIME_SERVER_PORT||'7373'; fetch('http://127.0.0.1:'+port+'/__runtime_healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "node_modules/vite/bin/vite.js"]
