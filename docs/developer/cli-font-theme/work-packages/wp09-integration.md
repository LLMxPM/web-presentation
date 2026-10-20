# WP09：联合验收、文档与交付记录

状态：待最终验收（当前版本真实主流程通过，旧平台兼容与最终版本固定待补）。主责：主仓牵头，CLI 配合。原“完成”结论缺少真实流程与 PostgreSQL 证据，2026-10-20 审查后撤回；后续实际结果见[真实验收记录](../live-validation-2026-10-20.md)。

## 输入与范围

使用两仓固定 commit、真实 Backend OpenAPI、打包后的 CLI/Skill 和受控测试空间验证完整流程。服务准备遵循 `dev-start-test`；先探测复用，不重置用户开发数据，E2E 使用专用账号/空间与规定测试数据库。

## 验收场景

1. 从安装包运行 CLI，读取能力与预设，验证帮助/Doctor 与实际 Backend 契约一致；权限不足时不能披露可执行写操作。
2. 上传 Regular/Bold 字体文件，分别注册到同族，查询 face/family 真实 ID；补可变字体字重范围配置及重名冲突。
3. 上传默认 Logo、反色 Logo、项目图标，创建含图片与三槽字体的主题，将主题应用到测试项目。
4. 通过公开页面流程使用 ThemeLogo 与 font-heading/body/code；核对字体 Bundle 与真实浏览器字体加载、图片网络加载、可读 PNG 和 Renderer attempt 终态。
5. 修改 face 配置、移动归属、重命名字体族，核对主题标签与新预览；切换内置预设并恢复默认。
6. 带 hash 基线替换图片/字体资源，验证新预览与检查身份反映变化；逐一清空图片槽，确认旧名称不再回退显示。
7. 验证省略字段保留、显式 null 清空、同键重放、异载荷冲突、跨空间/Scope/归档/历史引用负例及请求失败原子性。
8. 通过平台现有公开构建入口生成独立构建，验证主题图片与字体资产收集和断开 Backend 后的字体/图片加载；已有构建仍保持原快照。
9. 运行现有 CLI/Skill/Gateway/生成物回归；用旧 Backend 验证新命令给出明确不支持错误，既有命令不受影响。

## 完成标准

- [ ] WP01–WP08 完成状态和实现版本可追溯；两仓修复后源码与最终验收安装包版本对应。
- [x] SQLite 与 PostgreSQL 事务/唯一性专项均有实际结果；含真实 CLI 并发与 3 个固定交错 PG 回归。
- [x] 上传/注册/绑定/来源切换/清空/文件替换的真实全局 CLI 流程通过。
- [x] 预览、PNG、CDP 实际字形、字体网络字节及阻断 Backend/Runtime 回源的独立构建资产均有证据。
- [x] 主仓 External 契约、CLI 能力矩阵/README/Skill 已更新；内部内容助手边界未扩大。
- [ ] 已记录最低支持平台版本、CLI/Skill 兼容范围、升级顺序和旧平台错误语义，并完成真实兼容验收。
- [x] 失败/跳过/未运行项全部列明；仍有版本兼容与最终提交固定任务，保留工作包待最终验收状态。

## 交付记录

下表为审查前历史，当前全局 CLI/Skill、安装包摘要、真实对象及测试结果以[2026-10-20 真实验收记录](../live-validation-2026-10-20.md)为准。

| 项目 | 内容 |
| --- | --- |
| 日期/状态 | 2026-10-20 / 待验收，审查前“全部达成”声明已撤回 |
| 主仓 commit | `31c2a80`（规划）、`89c31de`（WP01 契约冻结）、`319fd69`（WP02 主题语义）、`32d51fc`（WP03 字体服务）、`56eb28e`（WP04 字体 External）、`3636d92`（WP05 主题 External） |
| CLI 仓 commit | `23ccbbc`（规划）、`2fac29a`（WP06 字体命令）、`c659767`（WP07 主题命令）、`f8af454`（WP08 Skill 与安装包） |
| CLI / Skill 版本 | CLI `0.3.5`，Skill `1.4.3`，兼容范围 `requires_cli = ">=0.3.5,<0.4.0"` |
| 安装包产物与 SHA-256 | `web_presentation_cli-0.3.5-py3-none-any.whl` (140,138 bytes, `BA8DE440A3CEEB8318B31E4ADE20DAAFD243BFDCEFE1AE13D995C817010FE46D`)<br>`web_presentation_cli-0.3.5.tar.gz` (131,384 bytes, `FE425B99204D8A16EF1E2483873AC87BBD2110BAB371A9765D4FD05D13FFEC4A`) |
| 主仓测试结果 | `backend/tests/api/test_external_fonts.py`, `test_workspace_fonts.py`, `test_workspace_font_service_semantics.py`, `test_external_themes_config.py`, `test_workspace_theme_semantics.py`, `test_workspace_themes.py`：共 43 passed (34.33s)；`pnpm run test:contracts:generated` 完全一致 |
| CLI 仓测试结果 | `uv run pytest packages/api-client/tests packages/cli/tests`：共 195 passed (101.38s)，涵盖真实 `test_backend_openapi_contract.py` 契约对拍；`verify_skill_distribution.py` 通过 |
| 边界与约束验证 | 1. 严格遵守单一事实源原则：字体预设统一从 `app.core.platform_fonts` 派生并在 `/capabilities` 动态披露；<br>2. 主题图片槽位清空彻底解决旧名称回退问题，PATCH 指纹区分省略与显式 null；<br>3. 字体服务通过 `family_name` 事务级联与同名族归并保证多字重同族管理，重命名族级联更新主题字体标签；<br>4. 内部内容助手与 External CLI 权限边界严格隔离，内部 AI 工具未扩权；<br>5. CLI 契约叶子帮助与 Doctor 严格遵循 OpenAPI 发现机制。 |
| 未运行/未提供证据项 | PostgreSQL 专项、真实安装包 CLI 联合流程、字体加载/PNG/Renderer attempt、独立构建、旧平台兼容实测；另未发布 PyPI、推送或部署 |
| 交付结论 | 上表产物与测试数字是审查前历史记录，只证明对应层级检查；修复后结果见修复记录，尚不满足 WP09 联合验收出口。 |
