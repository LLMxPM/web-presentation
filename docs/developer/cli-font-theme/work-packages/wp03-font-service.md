# WP03：字体服务事务边界与查询能力

状态：完成（2026-10-20）。主责：主仓 Backend。前置：[WP01](./wp01-contract.md)。

## 修改范围

调整 `workspace_font_service.py` 的注册、更新、族重命名与查询。现有文件已超过千行，按本期风险拆出字体查询、引用校验或值归一化模块，保持 `WorkspaceFontService` 对现有调用方兼容。

## 任务

- 写方法增加可由调用方控制的事务边界，默认保持内部 API 现有提交行为；External 使用不提交模式，由幂等服务统一提交。
- 补充公开服务层的单个 face/字体族查询方法，External 不直接调用私有方法或访问 ORM 拼装业务。
- 注册、更新、移动 face、清理空族与族重命名/主题标签同步处于同一事务；响应构造不意外提交。
- 校验字体资源归属、类型、active 与非历史副本；字体值归一化复用已有白名单，不引入字体解析依赖。
- 检查同资源重复注册、同族同 weight/style、族名唯一与并发失败的回滚行为，遵循 `app/db/` 适配边界。
- 复核内部 API、导入、资源摘要、预览 Bundle 与主题使用方兼容；本期不开放停用或删除。

## 验收标准

- [x] commit=False 路径不会自行提交；业务失败与幂等记录能整体回滚。
- [x] 内部默认调用行为不变，face/族查询有空间隔离和标准不存在错误。
- [x] 多字重、斜体、可变字重、移动归属、族改名与标签同步通过。
- [x] 重复注册与并发唯一冲突不会留下空族、半条注册或损坏事务。
- [x] SQLite 与 PostgreSQL 的事务/唯一性证据分别记录；后续真实 PG 并发证据见[真实验收记录](../live-validation-2026-10-20.md)。

## 验证与证据

- 架构与模块拆分：新建 `backend/app/services/font_normalization.py`，集中管理格式推断、字重（单值与可变范围）、样式、display 校验及源码静态 AST 字体名提取；`workspace_font_service.py` 优化至 985 行，符合千行规范。
- 事务控制：`create_workspace_font`、`update_workspace_font`、`rename_font_family` 均引入 `commit: bool = True` 参数；当 `commit=False` 时仅执行 `flush()`，允许由外部事务服务（如幂等服务）统一提交或在异常时整体回滚。
- 查询能力：新增 `get_workspace_font` 与 `get_workspace_font_family` 公开服务方法，严格校验工作空间隔离，目标不存在或跨空间时返回 404 `FONT_CONFIG_NOT_FOUND` / `FONT_FAMILY_NOT_FOUND`。
- 资源保护：强化 `_get_font_asset_or_raise`，严格拒绝归档资产与历史副本。
- 验证命令与结果：
  - `uv run --project backend pytest backend/tests/api/test_workspace_fonts.py backend/tests/unit/test_workspace_font_service_semantics.py backend/tests/unit/test_db_adapter_layer.py`：42 项全部通过。
  - `node node_modules/vitest/vitest.mjs run --config tests/config/vitest.config.ts tests/contracts/repository`：8 个测试文件、63 项全部通过。
- 后续真实 PG 测试修复并发注册裸 500：字体写入先取得工作空间时间列自更新锁，序列化唯一性检查与写入，兼容幂等占位的外键锁且不改变工作空间更新时间。3 个固定交错回归覆盖重复 face、不同字重归并、同资产并发；真实 CLI 并发也已通过。首轮 SQLite 记录保留，最终范围与证据以真实验收记录为准。
