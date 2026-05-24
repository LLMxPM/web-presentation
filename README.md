<!-- 文件功能：项目首页文档，用于面向新成员、部署方和协作者介绍 web-presentation 的定位、能力、架构入口与文档导航。 -->
# web-presentation

`web-presentation` 是一个面向 Vue 演示页面、组件资产和可视化编排场景的云端构建平台。它把 **Editor 工作台**、**Backend 控制面**、**Runtime 预览/构建引擎** 和 **AI 辅助创作能力** 组合在一起，让团队可以在浏览器中完成页面创建、组件复用、主题配置、智能体辅助编辑、实时预览和发布构建。

> 配图预留：平台产品总览图或首页截图，可放置在这里。

## 项目定位

这个仓库不是单一前端项目，而是平台集成仓库：

- 维护 Backend、Editor、Runtime 的集成关系和接口边界。
- 承载平台级 Docker 编排、CI/CD、测试策略和部署说明。
- 通过 `runtime/` Git 子模块接入独立项目 `web-runtime-vue`，让 Runtime 同时保持独立演进和平台运行时形态。
- 沉淀页面、组件、资源、主题、样式、构建产物和 AI Agent 的控制面契约。

## 核心能力

- **云端页面管理**：支持工作空间、项目、页面、组件、资源、主题和样式的结构化管理。
- **实时预览链路**：Backend 生成无状态 preview artifact，Runtime 通过 Vite 插件加载远程模块并渲染 iframe 预览。
- **Runtime Kit 契约**：页面和工作空间组件只能通过 `@runtime-kit` manifest 引用公开基础能力；公开能力使用 `<ExportName>.v<整数版本>` 文件名锁定依赖，未带 `.vN` 的路径不允许进入工作空间源码。
- **发布构建**：Backend 调度 Runtime 生成标准化构建产物，产物由 Backend 统一托管。
- **AI 辅助创作**：Backend 基于 Agno 构建智能体运行时，为 Editor 提供项目、页面、组件和资源相关的助手能力。
- **容器化交付**：根仓发布单个平台镜像 `web-presentation`，Runtime 子仓库独立发布 `web-runtime-vue` 镜像。

## 架构概览

> 配图预留：控制面 / 数据面架构图，可展示 Browser、Gateway、Backend、PostgreSQL、Redis、Runtime 和对象存储之间的关系。

| 模块 | 角色 | 主要技术 | 说明 |
| :--- | :--- | :--- | :--- |
| Backend | 控制面 / 数据持久化 | FastAPI、SQLAlchemy、PostgreSQL、Redis、Agno | 负责业务 API、权限、预览 artifact、构建调度、产物托管和 AI Agent 运行时 |
| Editor | 管理工作台 | Vue 3、Vite、Pinia、Monaco Editor | 负责项目配置、页面编辑、组件管理、资源管理和预览交互 |
| Runtime | 预览与构建引擎 | Vite Core API、Vue 3 | 负责加载 Backend 下发的预览上下文、远程模块、配置包并执行构建 |
| Infra | 交付与运行环境 | Docker、Docker Compose、GitHub Actions | 负责本地依赖、生产编排、镜像构建和 Docker Hub 发布 |

详细架构、模块边界和目标业务流程见 [平台架构说明](./docs/platform-architecture.md)。

## 典型流程

1. 用户在 Editor 中维护项目、页面、组件、资源、主题和样式。
2. Editor 调用 Backend 保存业务事实，Backend 写入 PostgreSQL。
3. 预览时 Backend 创建 preview artifact，并签发短期上下文令牌。
4. Runtime 通过 `/__preview` 加载预览上下文、配置包和远程模块。
5. 发布构建时 Backend 调度 Runtime 执行构建，Runtime 上传 zip 产物回 Backend。

> 配图预留：预览与发布时序图，可放置在这里。

## 快速开始

准备本地基础服务：

```powershell
docker compose -f .\docker-compose.dev.yml up -d
```

安装根仓测试依赖并运行常用检查：

```powershell
pnpm install
pnpm run test:backend
pnpm run test:editor
pnpm run test:contracts
```

Runtime 是子项目，进入 `runtime/` 后使用它自己的脚本：

```powershell
pnpm --dir runtime install
pnpm --dir runtime check
pnpm --dir runtime test
pnpm --dir runtime build
```

更完整的本地开发、测试数据和 Redis 切换说明见 [开发与测试指南](./docs/development-guide.md)。

## 容器与发布

当前容器发布策略：

- 根仓发布一个平台镜像：`web-presentation`，同一镜像可分别启动 Backend 容器和 Editor Gateway 容器。
- Runtime 子仓库发布独立镜像：`web-runtime-vue`，并提供 `sha-<12位提交>` 标签供平台 Release 校验。
- 平台 Release 会先跑质量门禁，再检查当前 `runtime` 子模块 SHA 对应的 Runtime 镜像是否存在，最后推送 Docker Hub。

详细 CI/CD 与生产 compose 模板见 [CI/CD 与容器部署说明](./docs/deployment-cicd.md)。

## 文档导航

| 文档 | 内容 |
| :--- | :--- |
| [平台架构说明](./docs/platform-architecture.md) | 平台目标、模块职责、目标流程和 Runtime 子模块协作 |
| [开发与测试指南](./docs/development-guide.md) | 本地依赖、测试入口、测试数据和运行态维护 |
| [当前状态与路线](./docs/project-status.md) | 已落地能力、当前限制和后续方向 |
| [测试治理说明](./docs/testing-strategy.md) | L0-L3 测试分层、目录归属和 CI 策略 |
| [CI/CD 与容器部署说明](./docs/deployment-cicd.md) | 平台镜像、Runtime 镜像、Docker Hub 发布和生产 compose |
| [Runtime 项目说明](./runtime/README.md) | `web-runtime-vue` 子项目自身的能力、运行方式和对接文档 |

## 仓库结构

```text
web-presentation/
├── backend/                 # Backend 控制面服务
├── editor/                  # Editor 管理工作台
├── runtime/                 # web-runtime-vue Git 子模块
├── tests/                   # 根仓契约测试与 E2E smoke
├── docs/                    # 平台架构、开发、部署和测试文档
├── Dockerfile               # 平台单镜像构建入口
├── docker-compose.dev.yml   # 本地 PostgreSQL / Redis 入口
└── docker-compose.prod.yml  # 生产 compose 模板
```

## 当前阶段

平台已经具备 Backend、Editor、Runtime、AI Agent、主题/样式/资源/组件管理和容器发布的基础能力；仍在持续补齐更完整的资源中心、Dashboard、项目关联使用关系和 Runtime 反向回传能力。

更详细的能力清单见 [当前状态与路线](./docs/project-status.md)。

## License

当前仓库顶层内容采用 Apache License 2.0，见 [LICENSE](./LICENSE)。

`runtime/` 是独立项目 `web-runtime-vue` 的 Git 子模块，继续遵循它自身仓库内声明的许可证，见 [runtime/LICENSE](./runtime/LICENSE)。
