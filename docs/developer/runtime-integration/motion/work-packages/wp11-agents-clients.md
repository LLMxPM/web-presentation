# WP11 模型与外部客户端

状态：待验收（共用规范、External API 异步截图、CLI/MCP 适配与文档已实施；真实三入口联合验收与能力开放待 WP12）。主责：Backend AI / CLI / MCP。前置：[WP07](./wp07-asset-capabilities.md)、[WP08](./wp08-host-slideshow-sync.md)、[WP09](./wp09-capture-export.md)、[WP10](./wp10-runtime-kit-editor.md)。

## 输入与落点

内置助手与 External API 继续共用代码规范。CLI/MCP 在同级独立仓实现适配，主仓维护其依赖的 Backend HTTP 契约与集成记录。

## 交付

- 扩展共用动画规范及 Runtime Kit 查询说明：先读 capability，再查真实资源动作，创建定义与绑定，等待 mutation job，按选择器取帧。
- 沿用 tool_specs 单一工具目录与 get_code_standards；只有参数契约变化时才修改工具规格，不另建动画工具清单。
- External API 支持动作摘要、新放映配置和临时 motionSnapshot，复用权限、幂等、版本与异步任务，不直连 Runtime 或泄露内部回执/票据。
- CLI/MCP 从 OpenAPI/能力摘要得到新参数，旧服务或关闭能力明确报不支持，不丢字段重试成旧行为。
- 为独立仓提供工作树/提交版本、生成类型基线、往返样例和失败样例；主仓通过不等于两个客户端已交付。
- 规范与示例覆盖 B01–B08，明确静态截图不能证明声音或动画播放，无法访问真实环境时不编造诊断结论。

## 验证与通过条件

同一受控测试工作空间分别由内置助手、CLI 与 MCP 查询/创建/修改/等待/取帧，核对最终对象版本、计划摘要、默认海报与临时截图。

覆盖关闭能力、旧 Schema、未知片段、过期引用与恢复；更新 OpenAPI/参数 Schema 时运行生成漂移及工具规格防漂移检查。

## 交接

将三种入口的完整证据和未交付项提交 WP12。用户自定义整类型规范保持原覆盖行为，不批量覆盖用户设置。

## 实施记录

- 代码版本与交付面：
  - 主仓：共用动画规范改为 capability-first——`usePageTimeline`/`Asset*.v2` 未在 Runtime Kit 清单返回即视为未开放，`AssetModel.v1` 只展示静态姿态；明确默认海报与临时帧都是静态证据，不能证明声音、播放或设备端 reduced 效果。`tool_specs` 同步时间轴查询与 `timeline_end`/`timeline_timeout_ms` 约束，未新增第二份动画工具清单。
  - 主仓 External API：新增 `page.screenshot.job.create/status/content`，持久化 `motion_snapshot`、去重 hash、结果内容与 `applied_motion`；临时任务只保存本次结果、不更新页面默认截图指针，显式选择器要求回执 `applied_motion.status=applied`。能力关闭返回 409 `TIMELINE_UNSUPPORTED`，目标版本冲突返回 409 `PAGE_SCREENSHOT_TARGET_VERSION_CONFLICT`，未完成内容读取返回 409 `PAGE_SCREENSHOT_JOB_NOT_READY`。OpenAPI 与 Editor 生成类型已刷新（paths=269、schemas=368）。
  - CLI `0.3.5`：`wp page screenshot` 新增 `--motion-timeline-id`、`--motion-label|--motion-at-ms`、`--motion-offset-ms`、`--motion-visual-mode`、`--target-version`、`--timeout`、`--idempotency-key`；先读页面与工作空间 capabilities，未开放时以 `TIMELINE_CAPTURE_CAPABILITY_MISSING` 退出且不创建任务。`project slideshow update` 与 `project route update` 增加 `timeline_end`/`timeline_timeout_ms` 能力校验，缺失时以 `SLIDESHOW_TIMELINE_CAPABILITY_MISSING` 拒绝写回而非降级为 `timer`。CLI 能力矩阵与 Skill 校验参考已更新。
  - MCP `0.1.0`：未新增工具，扩展 `wp_get_page_screenshot` 的 `motion`、`target_version`、`job_id`、`wait_seconds`、`idempotency_key`；新增三个 binding，支持创建、轮询、按 `job_id` 恢复与读取内容。能力关闭返回 `TIMELINE_CAPTURE_UNSUPPORTED`，未完成返回 `PAGE_SCREENSHOT_JOB_PENDING`，不返回占位图或回退 latest；媒体基线文档已更新。
- 实际命令与结果（2026-10-21）：
  - 主仓 `uv run --project backend pytest -c backend/pyproject.toml backend/tests/api/test_external_screenshot_jobs.py backend/tests/api/test_page_screenshot.py backend/tests/unit/test_page_screenshot_job_service.py backend/tests/unit/test_mutation_screenshot_dto.py backend/tests/unit/test_page_screenshot_queue_worker.py backend/tests/integration/test_sqlite_migration.py -q` → 33 passed。
  - 主仓 `uv run --project backend pytest -c backend/pyproject.toml backend/tests/api/test_external_api_v1.py backend/tests/api/test_external_screenshot_jobs.py -q` → 13 passed。
  - 主仓 `pnpm run test:contracts:generated` → paths=269、schemas=368，当前 Backend 与提交契约生成物一致。
  - CLI `uv run pytest packages/cli/tests -q` → 180 passed。
  - MCP `WP_MCP_BACKEND_OPENAPI=.tmp/merged-openapi.json uv run pytest tests/contracts/test_motion_screenshot_tools.py -q` → 4 passed；`wp-mcp-check-contract --openapi-file .tmp/merged-openapi.json` → 78 bindings / 73 HTTP 路由，document sha256 `2196aae6e0ff4d7ebb48468c21557781bb4ca5356a63c16cc225b5883c319761`。
  - MCP 完整套件 `uv run pytest -q` → 319 passed、9 failed；失败均为既有跨仓基线漂移（`page.get.source`/组件编辑基线、`project.list` 限制、Job 取消元数据、放映配置 DTO），不属于本包改动；本包 motion 用例与契约检查通过。
- 未覆盖项与后续接手：
  - 能力仍关闭（`TIMELINE_CAPABILITY_ENABLED=False`、`TIMELINE_CAPTURE_SNAPSHOT_ENABLED=False`），本包只验证关闭能力的准确失败语义，未完成真实 Backend → Renderer → Runtime 指定时刻截图。
  - 同一受控工作空间分别由内置助手、CLI 与 MCP 查询/创建/修改/等待/取帧的联合验收未执行，归 WP12。
  - 当前 dev 生成 OpenAPI 未携带 MCP 基线所需的 `x-wp-operation`；本次 MCP 验证使用固定 CI 基线元数据与当前生成物的临时合并件，跨仓生成物基线与固定主仓 commit 的收口仍属 WP12/发布流程。
  - CLI/MCP 文档已覆盖新参数、能力失败与静态证据边界，但未发布新包或更新已安装 Skill；发布动作不在本包内。
