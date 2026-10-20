# WP05：主题 External 创建、更新配置一致性

状态：完成（2026-10-20）。主责：主仓 Backend / 契约。前置：[WP01](./wp01-contract.md)、[WP02](./wp02-theme-semantics.md)。

## 修改范围

调整 External 主题创建/更新 DTO、路由字段转交、operation 说明与契约生成物。平台主题模型、内部 AI 工具 Schema 和工具说明不因本包扩权。

## 任务

- 为 External 创建/更新复用同一组图片/字体设计字段与校验，避免复制第二套字段枚举与规则。
- 创建请求将全部已支持字段正确转交内部服务，保留 palette 省略默认值与 key 不可变规则；更新仍使用部分字段语义。
- 拒绝未知/不可写字段，不能写任意字体名、路径、URL 或整段 theme YAML。
- 更新指纹保留字段是否显式提交；同键下“省略”和“null”、不同槽位恢复等语义不同的输入必须冲突。
- 按 WP01 的存量幂等记录兼容方案实施，避免指纹升级造成旧请求重复执行或无解释冲突。
- 同步 operation 说明、公共契约、共享样例和 codegen，为 WP07 提供明确版本。

## 验收标准

- [x] 主题可以一次创建图片与三槽字体配置，响应、读取与内部配置一致；复制保留绑定。
- [x] 更新省略/null/来源切换/默认恢复与共享真值表完全一致。
- [x] 同键同输入重放，省略与显式 null 同键冲突；失败不部分更新。
- [x] 旧创建请求、默认色板、名称/说明/色板更新及 THEME_KEY_IMMUTABLE 回归通过。
- [x] 现有幂等记录兼容证据、HTTP DTO 生成物与真实 OpenAPI 对拍通过。

## 验证与交接

- `uv run --project backend pytest backend/tests/api/test_external_themes_config.py`（4/4 通过）
- `uv run --project backend pytest backend/tests/api/test_workspace_theme_semantics.py backend/tests/api/test_external_api_v1.py`（15/15 通过）
- `pnpm exec vitest run tests/contracts/editor-api-types-drift.test.ts`（4/4 通过）
- `Set-Location c:\code\wp\web-presentation-cli; uv run pytest packages/cli/tests/test_backend_openapi_contract.py`（1/1 通过）
- 未运行项：完整 E2E 浏览器录屏留待 WP09 统一执行。

