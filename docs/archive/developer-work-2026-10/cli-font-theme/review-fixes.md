# CLI 字体与主题配置审查修复记录

日期：2026-10-20。两仓分支：`feature/cli-font-theme`。本次处理代码审查发现的问题，保留 WP09 待验收状态，不将定向测试或安装包检查当成真实渲染/双库验收。

## 修复范围

| 问题 | 修复与回归 |
| --- | --- |
| 旧主题 key 无法重放 | 创建恢复补齐默认值后的指纹；更新采用版本化显式字段集，兼容已完成旧结果，测试确保不覆盖对象后续修改 |
| Skill 契约错误 | 使用 payload-file 注册、动态发现真实预设、以字体资源逻辑名调用 Runtime helper；真实文档命令和 JSON 进入跨仓测试 |
| 验收声明缺少证据 | 两仓规划、工作包和交付状态改回待联合验收，历史包摘要不代表当前修复版本 |
| CLI 族名缺失 | 响应统一读取 font_family；写入仍使用 family_name；表格、JSON、raw 与真实 OpenAPI 响应字段一起验证 |
| 移走最后可用 face | 同事务按 ID 顺序锁定来源/目标族，检查主题引用与可用兄弟 face，拒绝时不残留目标空族；覆盖无兄弟/归档兄弟/active 兄弟、同族名称变体和内部停用/删除 |
| null 真值表漂移 | External 更新拒绝单独 null，恢复默认使用同槽双 null；内部 Editor 单 null 规则保持兼容；真实 API 消费共享正反例 |
| face null 被忽略 | 可写字段允许省略但拒绝显式 null，OpenAPI 同步表示非 nullable 的可选字段 |

## 幂等兼容边界

只为已完成记录返回第一次保存的响应，不重新执行写入、不接管 in_progress。最早的全量 PATCH 指纹丢失了字段存在性，无法还原旧 null 请求的真实意图，此类有歧义输入保守返回 409；客户端应查询目标核对，不自动更换 key 重发。新记录采用独立版本标记，不会误命中旧全量算法的兼容分支。

## 首轮审查验证（真实测试前）

按仓库 [dev-start-test 技能](../../../../.agents/skills/dev-start-test/SKILL.md)选择相关回归，使用隔离 SQLite 和临时安装环境，未重置开发数据。

| 检查 | 结果 |
| --- | --- |
| Backend 相关 API、字体/主题语义、幂等、数据库边界及 Skill 契约测试 | 108 passed |
| CLI 与 API Client 全量测试（包含真实 Backend OpenAPI 对拍、文档命令测试） | 197 passed |
| `pnpm run test:repository` | 8 个文件、63 passed |
| `pnpm run codegen:editor-api` / `pnpm run test:contracts:generated` | 生成成功，生成物检查通过 |
| CLI 离线构建 wheel/sdist、随包 Skill 清单校验、wheel 隔离安装 | 通过；安装后 CLI 0.3.5、包内 Skill 1.4.4 |
| 两仓 `git diff --check` | 通过 |

Backend 回归命令（在主仓运行）：

```powershell
uv run --no-sync --project backend pytest -c backend/pyproject.toml backend/tests/api/test_external_font_theme_regressions.py backend/tests/api/test_external_fonts.py backend/tests/api/test_external_themes_config.py backend/tests/api/test_workspace_theme_semantics.py backend/tests/unit/test_workspace_font_service_semantics.py backend/tests/api/test_workspace_fonts.py backend/tests/api/test_workspace_themes.py backend/tests/api/test_external_api_v1.py backend/tests/api/test_external_asset_replace.py backend/tests/unit/test_idempotency_service.py backend/tests/unit/test_db_adapter_layer.py backend/tests/contracts/test_cli_skill_examples.py --tb=short -q
```

CLI 检查命令（在 CLI 仓运行）：

```powershell
uv run --no-sync pytest packages/api-client/tests packages/cli/tests --tb=short -q
uv build --offline --package web-presentation-cli --out-dir .tmp/review-font-theme-dist
uv run --no-sync python packages/cli/tests/verify_skill_distribution.py .tmp/review-font-theme-dist
```

本机执行 pnpm 时增加 `--config.verify-deps-before-run=false`，复用已有依赖。候选产物位于 CLI 仓 `.tmp/review-font-theme-dist/`，只作为本轮源码快照的构建证据，未发布：

| 产物 | 字节数 | SHA256 |
| --- | ---: | --- |
| `web_presentation_cli-0.3.5-py3-none-any.whl` | 140661 | `C89165725DADC86EBB0AA38CFFC5A9E10A1E1F6552310688DC79CD7D4724D9BF` |
| `web_presentation_cli-0.3.5.tar.gz` | 132858 | `A04FD21D56534AC74B83E07B4353BC8D11CB29416E469CBC8530EACC985B7E69` |

首次审查时 Gateway/Nginx 检查因 Docker daemon 未运行而未执行，WP09 真实专项当时也未执行。该环境限制已在后续测试解除；首轮安装包隔离安装本身仍不代表真实平台或字体渲染验收。

## 后续真实验收

用户随后授权更新全局 Skill 并进行真实测试。全局 CLI 已升级为包含下载修复的 0.3.5，Skill 为 1.4.4；PostgreSQL、真实字体/主题流程、浏览器字形、PNG 刷新与独立构建已实际验证。测试又发现并修复字体 CSS 格式、ZIP 下载响应头、PG 并发注册及替换后的截图缓存问题。最终结果和替代本页首轮产物的摘要见[真实验收记录](../../../developer/projects/cli-font-theme/live-validation-2026-10-20.md)。

WP09 仍需补齐旧平台版本兼容实测和发布前最终 commit 固定。本轮不修改用户开发数据，不推送、发版或部署。
