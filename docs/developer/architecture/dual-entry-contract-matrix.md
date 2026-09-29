# 双入口契约矩阵（Top 操作）

> 状态：WS-E1 落地。覆盖页面读写、校验、预览、归档 Top 操作；不追求全矩阵。
> 对拍测试：`backend/tests/contracts/test_dual_entry_contract_matrix.py`。

## 1. 入口定义

| 入口 | 前缀 | 鉴权 | 消费者 | 路由源 |
| :--- | :--- | :--- | :--- | :--- |
| Internal | `/api` | 会话 Cookie/JWT | Editor、Runtime 内部调用 | `backend/app/api/routes/*.py` |
| External | `/api/v1` | PAT + scope + 幂等键 | CLI / Agent Kit / MCP | `backend/app/api/routes/external/*.py` |

两侧共用领域服务（`PageService` / `PreviewService` / `MutationJobService` / `CodeCheckService`），OpenAPI 同文档（FastAPI 自动 `/openapi.json`）。

External 操作注册表：`backend/app/core/external_operations.py`（`OPERATION_REGISTRY` + `_OPERATION_HTTP_CONTRACTS`）。

## 2. Top 操作对照

| 操作 | Internal | External | 响应对齐 | 有意差异 |
| :--- | :--- | :--- | :--- | :--- |
| 页面列表 | `GET /api/pages` | `GET /api/v1/projects/{id}/pages` | `PagedResponse[PageItem]` | 路径粒度：External 按项目过滤 |
| 页面读取 | `GET /api/pages/{id}` | `GET /api/v1/pages/{id}` + `/{id}/source` | `PageItem` | External 另有 `/source` 裸视图 |
| 页面创建 | `POST /api/pages` → `PageItem` | `POST /api/v1/pages` → **202** `ExternalMutationJobResponse` | **否** | Internal 同步；External 异步 Job + 幂等键 |
| 页面更新 | `PATCH /api/pages/{id}`（含 content/status） | `PATCH /api/v1/pages/{id}`（仅元数据） | `PageItem` | 源码走 `POST /pages/{id}/edits`（乐观锁 `base_version_no`） |
| 校验 | **无 HTTP 端点**（仅 AI 工具） | `POST /api/v1/validate/entity`、`POST /api/v1/pages/{id}/validate` | — | Internal 单侧缺失（登记缺口） |
| 项目预览 | `POST /api/projects/{id}/preview-artifacts` | `POST /api/v1/projects/{id}/preview-artifact` | `PreviewArtifactResponse` | 入参：`entry_descriptor` vs 扁平 `route` |
| 页面预览 | `POST /api/pages/{id}/versions/{n}/preview-artifact` | `POST /api/v1/pages/{id}/preview-artifact` | `PreviewArtifactResponse` | External 按当前版本，粒度不同 |
| 页面归档 | `DELETE /api/pages/{id}` → `MessageResponse` | `POST /api/v1/pages/{id}/archive` → `{"message"}` | **否** | HTTP 语义不同（DELETE vs POST）；均软删 `PageService.delete` |

## 3. 对拍口径

自动化对拍（`test_dual_entry_contract_matrix.py`）强制：

1. **注册表 ↔ 路由**：`_OPERATION_HTTP_CONTRACTS` 中 Top 操作的 method/path 在 OpenAPI `paths` 中真实存在。
2. **响应模型**：声明对齐的操作（页面列表/读取/更新、预览）两侧响应引用同一 schema 名或字段集合一致。
3. **有意差异登记**：创建（202 vs 200）、归档（DELETE vs POST）在矩阵中显式标注，测试断言差异仍然存在（防静默漂移成不一致）。
4. **校验缺口**：Internal 无 validate 端点这一事实被测试锁定，若有人补上 Internal 端点须同步改矩阵。

## 4. 已知缺口（不阻塞本项关闭）

| 缺口 | 处理 |
| :--- | :--- |
| Internal 无 validate HTTP 端点 | 产品选择：校验仅开放给 Agent。如需 Editor 同步调用再开 |
| 根契约测试大量 `toContain` 子串匹配 | 属 E2/E3 范围，逐步升级为 schema 往返 |
| 全矩阵（组件/资产/主题/样式等） | 按需追加，不在 E1 口径内 |

## 5. 维护约定

- 新增 Top 操作或改变两侧对齐关系时，先更新本表第 2 节，再改 `test_dual_entry_contract_matrix.py`。
- External 侧新操作仍以 `external_operations.py` 为单一事实源；本表不复制 scope/幂等细节。
- 有意差异必须写明「为什么」；若差异原因消失，应把两侧收敛并删掉该行。
