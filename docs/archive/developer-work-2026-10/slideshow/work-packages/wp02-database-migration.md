# WP02：模型列与双库迁移

状态：完成（2026-10-17）。阶段：M0。主责：Backend。
上层工作项：B01（模型/迁移）；详见[模块计划](../backend.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP01](wp01-contract-fixtures.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：Project 项目 JSON、ProjectRoute 两组可空覆盖及 Alembic 迁移；旧项目默认回填和新建 ORM 默认值。
- 交付物：SQLite/PostgreSQL 都能升级和读写的放映存储结构及降级边界说明。
- 提交边界：不在模型层复制生效值，不在服务层新写方言分支。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：旧项目仍为手动翻页、fade 400ms；旧路由为空覆盖；不改页面源码或样式快照。
- [x] 验证范围：空库/已有库迁移、双库读写与迁移行为回归。
- [x] 关联验收：A01、A08；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP02：模型列与双库迁移`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录

- 交付代码：`app/core/slideshow_defaults.py`（默认值单点）；`Project.slideshow_config_json`（非空 JSON，ORM/库双默认）；`ProjectRoute.transition_json`、`advance_json`（可空覆盖）；迁移 `20261017_0100_slideshow_settings.py`。
- 严格性：项目列 `NOT NULL` 且库默认值为完整 JSON；旧项目升级即获得 fade 400ms、manual 5000ms、loop/auto_start=false；旧路由两组覆盖保持 `NULL` 继承。
- 边界：模型不保存派生生效值；迁移不使用方言分支；不改页面源码、样式或既有数据。
- 验证：`pytest tests/unit/test_slideshow_storage_schema.py` → 3 passed（SQLite/PostgreSQL DDL 默认值对拍）；`pytest tests/integration/test_migration_behavior_contracts.py::test_slideshow_migration_backfills_defaults_and_keeps_route_overrides_empty` → 1 passed；`pytest tests/integration/test_sqlite_migration.py` → 41 passed（含空库升级 head）。未配置 `P4_POSTGRES_DATABASE_URL`，PostgreSQL 真实库迁移未运行。
- 证据：迁移测试覆盖“旧项目回填 + 旧路由空覆盖 + 新项目库默认值”三类行为。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
