# WP04：字体 External API、权限与能力发现

状态：完成（2026-10-20）。主责：主仓 Backend / 契约。前置：[WP01](./wp01-contract.md)、[WP03](./wp03-font-service.md)。

## 修改范围

新增独立字体 External 路由与 DTO，接入 `external/__init__.py`、`core/external_operations.py` 和 capabilities。避免将完整字体管理继续塞进 Runtime Kit 的 catalog 路由；迁移现有字体列表时保持路径与行为兼容。

## 任务

- 按冻结契约交付 face 列表/详情/注册/更新、family 列表/详情/重命名。
- 外部 DTO 显式约束可写字段，拒绝未知字段、status/asset_id 越界更新与非法 null；不透传内部删除/停用参数。
- 全部操作登记 Scope、HTTP 路径和幂等要求，能力清单从注册表派生，新增写操作复用统一幂等事务。
- 能力响应提供真实的字体预设目录，与 Schema/服务校验同源；operations 依当前凭证权限过滤。
- 核对响应中的真实 ID、字体配置、文件资源名；保留现有列表兼容，下载沿用 External 资源文件鉴权入口。
- 同步公共契约、共享正反例与 HTTP DTO 生成物；为 WP06 提供完整主仓 commit 和 OpenAPI 摘要。

## 验收标准

- [x] Scope 不足、空间越权、非字体资源、重复注册/族名、无效格式/字重/样式/显示策略有稳定错误。
- [x] 同键同输入重放、同键异输入冲突、失败回滚与并发请求通过。
- [x] 对象空间隔离生效，查询/更新不暴露其他空间对象；能力响应不提前披露未装配操作。
- [x] 创建后返回 font_id/family_id；修改归属/族名后主题与 Bundle 一致。
- [x] codegen、生成物检查、operation/OpenAPI 防漂移和现有字体列表回归通过。

## 验证与交接

- `uv run --project backend pytest backend/tests/api/test_external_fonts.py`（3/3 通过）
- `uv run --project backend pytest backend/tests/api/test_external_api_v1.py backend/tests/api/test_external_contract_gaps.py`（25/25 通过）
- `pnpm exec vitest run tests/contracts/editor-api-types-drift.test.ts`（4/4 通过）
- `Set-Location c:\code\wp\web-presentation-cli; uv run pytest packages/cli/tests/test_backend_openapi_contract.py`（1/1 通过）
- 未运行项：完整 E2E 浏览器录屏留待 WP09 统一执行。

