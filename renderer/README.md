# Renderer

Renderer 是独立的远程 Chromium 执行服务，负责页面截图、渲染诊断与浏览器生命周期管理，不连接平台数据库。Python 包名为 `wp_renderer`，与 Backend 的 `app` 共存于根 uv workspace。

## 本地运行

从仓库根目录执行：

```powershell
uv sync --all-packages --all-groups --all-extras --locked
uv run --project renderer playwright install chromium
uv run --project renderer uvicorn wp_renderer.main:app --host 127.0.0.1 --port 7400
```

Linux 首次安装使用 `playwright install --with-deps chromium`。配置按进程环境、`renderer/.env`、根 `.env` 的优先级读取，不受启动目录影响。先执行 `pnpm run env:check` 检查跨服务配置。

Backend 的 `RENDER_WORKERS_CONFIG` 必须包含本服务的 `RENDER_WORKER_ID` 和可达地址。两侧使用相同的 `RENDER_SERVICE_CREDENTIAL` 或凭据文件及 `RENDER_PROFILE_DIGEST`。空值、缺失文件和占位密钥会阻止服务启动。

`/livez` 检查进程存活，`/readyz` 返回槽位状态；控制 API 还需要服务身份令牌。详细契约见 [远程渲染设计](../docs/developer/backend/remote-render-service-design.md)。

## 测试与交付

```powershell
pnpm run test:renderer
pnpm run test:python-workspace
pnpm run test:render-e2e
docker build -f renderer/Dockerfile -t web-presentation-renderer:local .
python scripts/contracts/check-image-startup.py --image web-presentation-renderer:local --variant renderer
```

`test:renderer` 运行不依赖真实浏览器的单元测试；`test:render-e2e` 准备隔离的 E2E 数据和四个服务，通过 Editor 发起截图，检查任务成功及 PNG 内容、尺寸，依赖 Node 与 Python 两套 Playwright Chromium。

Release 与平台、Runtime 同时发布 `llmxpm/web-presentation-renderer:<release_tag>`。稳定版本同时更新 `latest`；部署及回滚时固定同一发布版本的镜像组合。
