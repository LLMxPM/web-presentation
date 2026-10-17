# WP22：媒体模式 Schema 与预览权限链

状态：已完成（2026-10-18）。阶段：M2。主责：Backend / Editor 预览桥。
上层工作项：B06（契约/授权）、E04（权限）；详见[模块计划](../backend.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP21](./wp21-m1-integration-release.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：advance 媒体扩展、旧数据归一化与超时字段；Editor→桥接宿主→Runtime 的 autoplay/fullscreen 委派。
- 交付物：供播放器和表单接入的媒体配置 DTO、兼容样例和可验证的跨域权限链。
- 提交边界：不实现播放调度或自动续签，不扩大 Cookie/CORS。M2 能力声明由 WP30 最后开放。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：缺省/升级符合统一契约；仍禁止跨源消息绕过；仅交付结构不提前声明 media_end 或 presenter 已可用。
- [x] 验证范围：媒体 Schema、默认/旧数据读取、能力不披露、预览桥来源与跨域负例；真实浏览器 autoplay 播放和受阻提示留给 WP24/WP30。
- [x] 关联验收：A05、A19；A05 由本包 API/能力测试覆盖，A19 的播放控制器与真实受阻恢复由 WP24/WP30 执行。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP22：媒体模式 Schema 与预览权限链`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- Schema：`SlideshowAdvance` 增加 `media_end` 与 `media_timeout_ms`（默认 300000，范围 1000–3600000），三种模式保留完整结构；默认配置、旧项目/旧路由读取补齐该字段；Runtime 映射增加 `mediaTimeoutMs`。
- 能力门禁：`SLIDESHOW_SCHEMA_VERSION = 2`，但 `advance_modes` 仍由可执行模式常量派生为 `manual`/`timer`；`media_end` 写入门禁与能力开放共用同一常量，WP30 完成执行器与真实验收后再解除。AI 工具手册同时隐藏未开放的 `media_end` 枚举。
- 预览权限：Bridge 宿主 iframe 与 Editor 预览 iframe 补齐 `autoplay`/`fullscreen` 委派；消息桥仍只接受校验后的窗口、来源和 artifact，未新增绕过来源校验的指令。
- Editor 兼容：生成类型更新后，表单草稿会保留 `media_timeout_ms`，避免 M2 结构在旧表单保存时丢失；媒体模式表单项仍由 WP27 交付。
- 验证：`uv run --project backend pytest -q backend/tests/unit/test_slideshow_schema.py backend/tests/unit/test_private_delivery_regressions.py backend/tests/api/test_project_slideshow_settings.py backend/tests/api/test_project_route_slideshow.py backend/tests/api/test_project_preview_slideshow.py backend/tests/api/test_project_template_package_slideshow.py backend/tests/api/test_external_project_slideshow.py backend/tests/integration/ai/test_ai_generic_business_tools.py` → 76 passed；`pytest ... catalog_routes_versioning_cases_1.py test_generic_business_tools.py test_slideshow_storage_schema.py` → 39 passed；迁移默认值与路由/模板/权限回归同组定向测试通过；`pnpm --dir editor test` → 153 files/843 passed；`pnpm --dir editor check` 通过；`pnpm run test:contracts` → 104 passed；`pnpm run codegen:editor-api` 后 `pnpm run test:contracts:generated` 通过。
- 未运行：真实 Chromium 的 autoplay/fullscreen 落播与 A19 受阻/错误恢复（由 WP24/WP30 执行）；本轮未修改构建产物鉴权、票据或代理链路。
- 产物：测试命令输出与摘要保存在 `.tmp/wp22/`。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
