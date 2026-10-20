# WP01：契约、共享样例与兼容边界冻结

状态：完成（2026-10-20）。主责：主仓 Backend / 契约；CLI 参与消费复核。前置：无。

## 输入与范围

以[实施规划](../implementation-plan.md)的目标表为候选，复核现有 `schemas/font.py`、`schemas/theme.py`、External 路由、operation 注册表、字体/主题服务及 CLI 严格帮助机制。

交付公共契约章节与共享正反例，不实现业务路由、CLI 命令或自动注册。契约正文落在 `docs/developer/reference/external-agent-api.md`，新增能力显式标为待实现；样例放主仓 `tests/fixtures/cli-font-theme/`，CLI 契约测试以固定主仓版本消费，不复制内部 Python 模型。

## 任务

- 冻结路径、operation key、Scope、分页/筛选、注册项与族响应、外部可写字段、错误码和幂等要求。
- 列出 asset_id/font_id/family_id 的区别；确定同资源/face 签名/族名冲突的大小写、空白、唯一性与并发语义。
- 冻结三个字体槽的省略、family/preset 单独 null、同时 null、来源切换、双非空冲突真值表；确定图片 ID 清空与历史路径兼容行为。
- 冻结预设的能力发现字段与 Schema 允许值，来源统一到 `platform_fonts.py`；不新增独立手写枚举。
- 确定失效引用的处理：新增/更换引用拒绝归档资源、历史副本和无 active face 的字体族；只读查询仍允许发现并修复存量坏引用。
- 明确 PATCH 指纹的字段存在性、存量幂等记录兼容策略和事务/并发用例；无安全迁移策略时不能让旧 key 静默重复执行。
- 检查现有数据约束能否支撑目标，记录不迁移的依据；需要迁移时补双库工作与验收。
- 明确本期不开放 status 写入、注销、硬删除、自动推断与内部 AI 工具扩权。

## 验收标准

- [x] 接口表、字段表、真值表、Scope、错误与操作注册命名无待猜项。
- [x] 正反例覆盖完整流程、空更新、null、重复 face、可变字重、非法类型、跨空间和失效引用。
- [x] 创建/更新共用设计字段定义，主题 key 不可变，旧列表/默认色板行为保持兼容。
- [x] CLI 侧确认可从真实响应获得 font_id/family_id，帮助和 Doctor 可发现全部契约。
- [x] 已记录事务策略、幂等存量兼容与双库验证安排；候选决策回写实施规划。

## 证据回填

- 冻结契约正文：`docs/developer/reference/external-agent-api.md`（4.1 字体能力自省、5.1 字体与字体族管理、5.1 主题图片与三槽字体配置及真值表）。
- 共享正反例路径：`tests/fixtures/cli-font-theme/font-theme-contract-cases.json`。
- 数据库与约束评估：`workspace_themes`、`workspace_font_families`、`workspace_font_configs` 现有唯一约束（资产单次注册、同族同字重样式唯一、族名同空间唯一）完备，确认无需新增迁移。
- 幂等指纹策略：PATCH 请求计算指纹时使用 `model_dump(exclude_unset=True)`，同键下省略与显式 null 形成异指纹冲突（409）。
- 验证：运行 `node node_modules/vitest/vitest.mjs run --config tests/config/vitest.config.ts tests/contracts/repository`，8 个测试文件、63 项全部通过；CLI 仓全量回归 184 项全部通过；`git diff --check` 通过。
- 未运行项：业务路由与服务实现（归属 WP02–WP05）。
