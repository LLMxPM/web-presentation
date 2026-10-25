# WP02：主题清空语义、字段存在性与引用校验

状态：完成（2026-10-20）。主责：主仓 Backend。前置：[WP01](wp01-contract.md)。

## 修改范围

围绕 `workspace_theme_service.py` 及必要的公共引用校验辅助模块修改，不新增主题字段或 CLI 命令。该服务已经较长，新增复杂逻辑应拆成主题引用解析模块，不做全仓重构。

## 任务

- 区分未提交图片 ID 与显式 null；清空 Logo/反色 Logo/项目图标时同步清理持久化名称，禁止 Runtime 从旧名称继续解析。
- 保留未修改字段和现有历史路径兼容；清空与替换后核对主题详情、resolved YAML 和 Runtime 配置。
- 按 WP01 真值表处理 family/preset 切换、默认恢复、双来源冲突；不按当前值猜测客户端意图。
- 新增/更换图片引用校验工作空间、资源类型、active 状态、非历史副本；字体族需存在可用 face，且 face 对应资源有效。
- 对存量失效引用保留可读与清空修复路径；名称/色板的独立修改是否受影响按 WP01 冻结规则执行。
- 复核资源、字体与主题的快照/检查身份：新增预览反映修改，已有独立构建保留原快照；发现缓存遗漏纳入本包最小修复。

## 验收标准

- [x] 三个图片槽逐一覆盖省略保留、替换、显式 null，清空后 ID、名称、YAML 与渲染配置一致。
- [x] 三个字体槽的来源切换和默认恢复按共享真值表通过，未提交槽位保持原样。
- [x] 归档/历史/跨空间/类型错误与无可用 face 的新绑定被拒绝；请求失败不部分写入。
- [x] 存量失效引用可查询、替换或清空，历史路径兼容有回归证据。
- [x] 现有主题复制、字体族改名、默认主题和预览/构建收集回归通过。

## 验证与证据

- 架构与模块拆分：新建 `backend/app/services/theme_reference_resolver.py`，承载图片资产校验、字体族 active face 校验、安全只读加载和三槽真值表解析；`workspace_theme_service.py` 缩减至 758 行，符合千行规范。
- 缺陷修复：彻底修复显式清空图片 ID 时回退旧 `logo_path` / `invert_logo_path` / `project_icon_name` 的问题；显式传 null 清空时同步将路径与名称清空为 null，禁止向 Runtime 泄漏历史名称。
- 容错读取：`safe_load_theme_relations` 针对只读场景优雅处理失效存量引用，防止主题列表或详情报错崩溃，并允许用户后续通过 PATCH 修复清空。
- 验证命令与结果：
  - `uv run --project backend pytest backend/tests/api/test_workspace_themes.py backend/tests/api/test_workspace_theme_semantics.py`：10 项全部通过。
  - `uv run --project backend pytest backend/tests/unit/test_db_adapter_layer.py`：16 项全部通过，数据库适配层边界无漂移。
  - `node node_modules/vitest/vitest.mjs run --config tests/config/vitest.config.ts tests/contracts/repository`：8 个测试文件、63 项全部通过。
- 遗留与交接：实际渲染与截图证据在 WP09 联合验收。未实现 External 路由调整（由 WP05 承接）。
