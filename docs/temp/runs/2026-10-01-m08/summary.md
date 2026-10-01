<!-- 文件功能：记录架构收尾计划第三批（M08 用户行为与跨仓回归、工程候选 M01 闭环）验收过程、实测命令、输出与门禁结论。 -->
# 第三批工程收尾验收报告 (M08 / M01)

- 演练日期：2026-10-01
- 主仓提交基线：`4305053add4990ced5ef04750a8b1cae9528d2e0`
- Agent Kit 提交基线：`f6a75ecd434ac8a07f5f16a6b164b4d8d813c686`
- 关联计划：[架构收尾计划 2026-10-01](../../plans/architecture-closeout-plan-2026-10-01.md)

---

## 1. 目标与范围

根据计划第 5 节与第 7 节，第三批（工程阶段收尾）必须达成以下目标：
1. **M08 用户行为与跨仓回归**：
   - 资产筛选/详情/批量；
   - AI 进程停止文案与会话重新发起；
   - 富文本自闭合节点不绑定写入与成对空节点可编辑；
   - 诊断降级不使整页失败；
   - 跨用户工作空间写入必须拒绝；Internal 与 External 两入口覆盖读取、写入、异步任务及归档；
   - 同级 Agent Kit 固定 Git ref、配置与契约版本，运行 CLI/Skill 真实回归测试。
2. **M01 最终工程候选与契约回归**：
   - 契约单源化与防漂移（331 个 API 类型与 OpenAPI 保持一致）；
   - 网关契约（Gateway OpenAPI、上游 503 透传与 SPA 回退）；
   - Docker 构建上下文敏感文件排除规则；
   - Python workspace 全成员统一依赖导入与部署探针通过。

---

## 2. 详细实测与执行命令

### 2.1 M08: 跨用户/跨工作空间双入口隔离（四象限防御）

- 测试用例：`backend/tests/integration/test_dual_entry_workspace_isolation.py`
- 验证命令：
  ```powershell
  uv run --project backend pytest backend/tests/integration/test_dual_entry_workspace_isolation.py
  ```
- 结果：**2 passed in 8.01s**
- 详细覆盖矩阵：
  | 入口 | 操作象限 | 触发端点 | 请求意图 | 预期拦截与状态码 | 实测结果 |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | **Internal** (`/api/...`) | 读取 (Read) | `GET /api/workspaces/{id}`, `/api/projects/{id}`, `/api/pages/{id}` | User B 尝试读取 User A 的工作空间、项目及页面 | 403 `WORKSPACE_ACCESS_DENIED` | 通过 (403) |
  | **Internal** (`/api/...`) | 写入 (Write) | `POST /api/pages`, `PATCH /api/pages/{id}` | User B 尝试向 User A 的空间/项目注入新页面或修改已有页面 | 403 `WORKSPACE_ACCESS_DENIED` | 通过 (403) |
  | **Internal** (`/api/...`) | 异步任务 (Async Job) | `POST /api/projects/{id}/build-jobs` | User B 尝试对 User A 的项目发起构建任务 | 403 `WORKSPACE_ACCESS_DENIED` | 通过 (403) |
  | **Internal** (`/api/...`) | 归档 (Archive) | `DELETE /api/pages/{id}`, `DELETE /api/projects/{id}` | User B 尝试删除/归档 User A 的页面或项目 | 403 `WORKSPACE_ACCESS_DENIED` | 通过 (403) |
  | **External** (`/api/v1/...`) | 读取 (Read) | `GET /api/v1/projects/{id}/pages`, `GET /api/v1/pages/{id}` | User B (持有 ws_b PAT) 试图读取 User A 空间/页面 | 403 `WORKSPACE_NOT_AUTHORIZED` / `WORKSPACE_ACCESS_DENIED` | 通过 (403) |
  | **External** (`/api/v1/...`) | 写入 (Write) | `POST /api/v1/jobs/mutations/pages` | 试图通过页面 Mutation 向 User A 空间注入页面 | 403 `WORKSPACE_NOT_AUTHORIZED` | 通过 (403) |
  | **External** (`/api/v1/...`) | 异步任务 (Async Job) | `POST /api/v1/jobs/mutations/components` | 试图通过组件 Mutation 向 User A 空间创建组件 | 403 `WORKSPACE_NOT_AUTHORIZED` | 通过 (403) |
  | **External** (`/api/v1/...`) | 归档 (Archive) | `POST /api/v1/pages/{id}/archive` | 试图跨空间归档他人页面 | 403 `WORKSPACE_NOT_AUTHORIZED` / `WORKSPACE_ACCESS_DENIED` | 通过 (403) |
  | **External** (`/api/v1/...`) | 批量归档 (IDOR 防御) | `POST /api/v1/pages/batch-archive` | 在 ws_b 下试图批量归档属于 ws_a 的 page_a | 403 跨空间越权拦截 | 通过 (403) |

### 2.2 M08: 用户端交互与降级行为（Editor / Runtime）

- **资产筛选/详情/批量**：
  - Editor 单元测试覆盖：`src/api/assets.test.ts`（19 项通过）
- **AI 进程停止文案与重新发起**：
  - Editor 状态机覆盖：`src/components/agent/agent-run-state.test.ts`（37 项通过，验证停止状态投影与重新发起）
  - Backend 覆盖：`backend/tests/integration/test_ai_run_stop_semantics.py`
- **富文本自闭合节点不绑定写入与成对空节点可编辑**：
  - 前端规则覆盖：`src/utils/page-visual-edit-rich-text.test.ts`（2 项通过）
  - 后端 Schema 校验覆盖：`backend/tests/unit/test_page_visual_edit_schema.py` (`test_rich_text_binding_should_allow_empty_insertion_range`)
- **诊断降级不使整页失败**：
  - 前端预览生命周期：`src/composables/useRuntimePreviewLifecycle.test.ts`（2 项通过）
- **Editor 全量门禁**：
  ```powershell
  pnpm run test:editor
  ```
  结果：**132 passed, 739 passed in 78.58s**
- **Runtime 全量门禁**：
  ```powershell
  pnpm run test:runtime
  ```
  结果：**91 passed, 607 passed in 19.02s**

### 2.3 M08: Agent Kit 跨仓回归

- 仓路径：`c:\code\wp\web-presentation-agent-kit`
- Git 提交：`f6a75ecd434ac8a07f5f16a6b164b4d8d813c686`
- 验证命令与结果：
  ```powershell
  uv run pytest packages/api-client/tests packages/cli/tests
  ```
  结果：**88 passed in 96.64s**
  ```powershell
  uv run --project packages/cli wp --help
  ```
  结果：正常输出全部 18 个一级命令，无丢失或异常。

### 2.4 M01: 契约与跨模块回归

- **CLI Skill 契约**：
  ```powershell
  pnpm run test:contracts:cli-skill
  ```
  结果：**1 passed in 4.17s**
- **代码生成与 OpenAPI 防漂移**：
  ```powershell
  pnpm run test:contracts:generated
  ```
  结果：331 个 API 类型与 Backend 生产 OpenAPI 100% 对齐。
- **根仓契约套件**：
  ```powershell
  pnpm run test:contracts
  ```
  结果：**12 passed, 41 passed in 3.24s**
- **Nginx Gateway OpenAPI 与透传契约**：
  ```powershell
  pnpm run test:contracts:gateway
  ```
  结果：OpenAPI 契约、上游 503 透传与 SPA 路由检查全部通过。
- **Docker 构建上下文排除规则**：
  ```powershell
  pnpm run test:contracts:docker-context
  ```
  结果：所有敏感文件、虚拟环境及构建临时文件排除规则验证通过。
- **文档与部署拓扑一致性**：
  ```powershell
  pnpm run test:repository
  ```
  结果：**4 passed, 13 passed in 0.51s**
- **Python Workspace 共装环境**：
  ```powershell
  pnpm run test:python-workspace
  ```
  结果：**17 passed in 22.19s**（包含部署探针默认视口对齐修复）。

---

## 3. 门禁结论与后续

| 门禁项 | 本轮状态 | 依据 |
| :--- | :--- | :--- |
| **M08** | **已关闭** | 双入口隔离四象限 403 强拦截验证完备；Editor 资产/富文本/AI停止文案全部通过（739 passed）；Agent Kit 88 项测试 100% 通过。 |
| **M01** | **工程阶段执行范围已关闭** | 契约防漂移（331 类型）、全套 Gateway、Docker Context、Repository 与 Workspace 共装测试全部通过；交付阶段仅待真实 arm64/最终模板镜像演练。 |
| **工程阶段整体** | **全部关闭** | 第零批、第一批（M04）、第二批（M02/M07）、第三批（M08/M01）工程门禁均已达成！ |
