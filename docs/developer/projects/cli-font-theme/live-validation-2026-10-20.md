# CLI 字体与主题真实验收记录（2026-10-20）

本轮使用全局安装的 CLI 和真实服务完成当前版本的主流程验收，包含实际字体字形、Renderer PNG、PostgreSQL 并发与独立构建。本页记录 2026-10-20 当时状态；2026-10-25 用户已确认新 CLI 连接当前旧版 Backend 的兼容实测通过，两仓修复已提交，发布安装包对账仍待做，见文末补记。

## 环境与版本

- 分支：两仓均为 `feature/cli-font-theme`，修复尚未提交、推送或发布。
- 主仓基线：`04ec9ab3ccecc91aed535e9eb2406727e5d23e90`；CLI 基线：`d960f70ff560505c513be04815f46c19853f5fba`。这些基线不包含本轮未提交修复。
- 主仓改动源码清单 SHA256：`96edc81bbe42e561662aa5ac52f7eabd2c420efeed66106954ce95236ad4a618`（19 个文件）；CLI：`874e658fc3ced7435e9c0ec3f3e3249808145e7d489ec4c624c016398f247c4d`（10 个文件）。清单包含改动/新增源码、契约及 CLI Skill，不包含本记录等验收文档。
- 全局 CLI 从 0.3.4 更新为本地候选包 0.3.5；全局 `web-presentation` Skill 从 1.4.2 更新为 1.4.4，`wp skill status --scope global` 为 `up_to_date`，内容摘要为 `sha256:0ab8abe3963ef3fad09e601ac4e2227f9907ea0c2fe65fd01f9eea9d85f3148d`。
- 按 [dev-start-test](../../../../.agents/skills/dev-start-test/SKILL.md)探测环境。应用服务原先均未启动，复用已启动的 Docker PostgreSQL/Redis，准备独立库 `wp_font_theme_20261020_e2e` 与 `wp_font_theme_pg_contract_20261020_e2e`。未修改 `.env`、未重置开发库。
- Backend / Editor / Runtime / Renderer 分别使用 8000 / 5173 / 7373 / 7400；AI 为 mock，字体、资源、数据库、预览、截图与构建均为真实执行。测试后保留隔离 E2E 服务。
- 测试 Profile：`font-theme-live-20261020`，未改变用户当前默认 Profile；测试 PAT 仅授权测试空间、一天有效。临时只读 PAT 已吊销并登出。
- 保存的真实 OpenAPI JSON 文件 SHA256：`6ab822a01aff2b996507ed8e150a2813dba15c608bd4afd81b7b5ba9740afa65`。

## 字体与真实对象

字体从用户提供的 [OSFCC](https://drxie.github.io/OSFCC/) 定位到 [Adobe 思源黑体官方仓库](https://github.com/adobe-fonts/source-han-sans)，可变字体来自 [Google Fonts Roboto Mono](https://github.com/google/fonts/tree/main/ofl/robotomono)。原始许可随下载文件保留在临时目录，字体二进制未入库。

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| SourceHanSansSC-Regular.otf | 16529832 | `f1d8611151880c6c336aabeac4640ef434fa13cbfbf1ffe82d0a71b2a5637256` |
| SourceHanSansSC-Bold.otf | 16963428 | `df2b90f5bcc6d01dfc964cec5f6d535d6b6aebd26ed7fd79a9c1b3f2112fcb6b` |
| RobotoMono 可变 TTF | 183700 | `66a80e79d17e4c7cabd162e2916578a4cc08fd19eef6e2a643305eae9c567b2b` |

真实对象：主测试工作空间 2、负例空间 3、项目 2、页面 2（`PG20261020002`）、主题 4（`font-theme-live`）。Regular/Bold face 为 1/2，共用 family 1；可变 face 为 3，family 为 2，注册字重范围 `100 700`。三张主题图片资源为 6/7/8。以上 ID 只属于本轮 E2E 库。

## 真实测试发现并修复的问题

| 问题 | 修复与证据 |
| --- | --- |
| OTF/TTF 已绑定但浏览器实际回退系统字体 | Runtime 将文件格式映射为 CSS `opentype` / `truetype`；增加四种格式回归。修复前 CDP 显示 Microsoft YaHei/NSimSun，修复后实际字形分别来自 SourceHanSansSC-Bold、SourceHanSansSC-Regular 与 RobotoMono，均为自定义字体；网络字节 SHA256 与上表一致。CSS 格式名称依据 [W3C 字体格式规范](https://www.w3.org/TR/css-fonts-4/#font-formats)。 |
| 构建成功但 CLI ZIP 下载报 Content-Type 缺失 | `download_file` 原先返回请求头，改为复制响应头；增加真实下载入口的 ZIP 成功回归。全局 CLI 下载构建 2 成功，长度与 SHA256 均和 Backend 一致。 |
| 并发注册同名族/相同 face 返回 500 | 字体写入在工作空间维度串行执行检查与写入；使用时间列自更新取得锁，保持更新时间不变，避免与幂等占位外键锁升级死锁。3 个 PG 回归通过；真实并发 CLI 为一笔成功、一笔 `FONT_CONFIG_DUPLICATE_FACE`。不同字重会归并到同族，同资产并发也返回明确冲突。 |
| 同名替换字体/Logo 后最新 PNG 仍为旧内容 | 检查与截图的共同主题指纹补入字体及 Logo 文件 hash/可用性。10 个项目/组件正反例覆盖替换失效、无关资源与 favicon 字节不影响画布身份；真实 PNG 分别随 Logo、字体独立替换变化，恢复字节后回到基线。 |

## 已通过的真实流程

1. 全局 CLI 的 Doctor、当前 Backend OpenAPI 叶子帮助、capabilities 和 Runtime Kit 查询；读取真实预设 token。
2. 字体上传 → 注册 → 同族多字重查询 → 可变字重注册 → 字体族改名和主题标签同步 → face 配置更新。重复注册、单 null、跨空间绑定均按契约拒绝。
3. 主题三槽字体与 Logo/反色 Logo/Icon 绑定并应用到项目；页面通过 `font-heading/body/code`、`ThemeLogo` 和静态资源名 `useAssetFontFamily` 消费。
4. 自定义字体 → 内置预设 → 同槽双 null 恢复默认 → 恢复自定义字体；实际浏览器分别确认字形来源及计算字重。
5. 逐一清空三张主题图片，确认返回字段和生成主题配置无旧名称回退，浏览器两个 Logo 均消失；之后恢复测试图片。
6. 使用当前 hash 基线替换字体和 Logo；真实预览确认字体文件变化，字体/图片替换前创建的独立构建仍保留原文件。
7. 同键创建/更新重放、省略字段保留、异载荷冲突；只读 Scope 不披露写能力且不能写入；归档及历史字体不能注册。
8. 两个真实 CLI 并发移走同族两个 face，始终保留主题所需的最后一个可用 face；失败事务不残留新空族，测试后恢复原族。最终锁实现已再次实测。

### PNG、attempt 与离线构建证据

| PNG 场景 | SHA256 |
| --- | --- |
| 最终修复基线 | `df965286f56f07d465ef3fac75d294e4529a439049ff934680741e5fd7d41cab` |
| 只替换 Logo | `8a21ba40217009dd428654c3cc6e44dcb6664e55dc2883266163062eacc41e5e` |
| 只替换 Regular 字体文件 | `47c5bdd6ced5f2a54fbb816bf46c681084fbc8858c982896247526948dced7b5` |
| 分别恢复原 Logo / 字体 | 两者均恢复为上述基线 SHA256 |

PNG 均为 1280×720，已打开复核。专用页面的 render request 1–8 均 `succeeded`，8 次物理 attempt 均 `terminal`、`cleanup_status=released`、`active_occupancy=0`；Renderer 最终 `/readyz` 为 `slot_state=idle`。

项目构建 2 / snapshot release 2 成功，attempt 为 `6db6b45124e540278aa22be60ae9b765`。ZIP 为 43369045 字节，SHA256 `cc9c39a92b7e51f74fd0669d064597cc35175d55f3237ec57d5d75d46e9d28bb`。解压后以独立静态 HTTP 服务运行，浏览器只允许该静态站点，阻断 Backend、Runtime 和外网回源；无回源请求、无页面错误，三份字体的实际字形/文件 hash 及两张 Logo 均正确。资源替换后再次运行同一旧构建，仍使用原文件。

## 最终自动化与分发结果

| 检查 | 实际结果 |
| --- | --- |
| 字体/主题、幂等、DB 边界、主题文件指纹、截图队列相关 Backend 回归 | 125 passed |
| PostgreSQL 认领、双库迁移、字体并发注册 | 13 passed，1 skipped；历史迁移 revision 尚无 thinking_enabled，非 PG 缺配置跳过 |
| CLI / API Client 全量（包含真实 Backend OpenAPI 对拍） | 198 passed |
| Runtime 字体注册测试 / Vue 类型检查 | 13 passed / 通过 |
| 真实 Nginx Gateway 契约 | 通过，包括文件出口阻断、授权构建产物、上游 503 及 SPA 路由 |
| wheel / sdist 构建与 Skill 清单检查 | 通过；修复后 wheel 已更新到全局 CLI 并参与真实测试 |
| 仓库文档/边界检查 | 8 个文件、63 passed；两仓 `git diff --check` 通过 |

PG 命令：

```powershell
$env:P4_POSTGRES_DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/wp_font_theme_pg_contract_20261020_e2e'
$env:P4_POSTGRES_REQUIRED='1'
uv run --no-sync --project backend pytest -c backend/pyproject.toml backend/tests/integration/test_pg_claim_contention.py backend/tests/integration/test_migration_behavior_contracts.py backend/tests/integration/test_pg_font_registration.py --tb=short -q -rs
```

Backend 125 项命令在[修复记录](../../../archive/developer-work-2026-10/cli-font-theme/review-fixes.md)的 108 项列表上追加 `backend/tests/unit/test_theme_asset_fingerprint.py`、`backend/tests/unit/test_code_check_fingerprint_builder.py`、`backend/tests/unit/test_page_screenshot_fingerprint_service.py`、`backend/tests/unit/test_page_screenshot_job_service.py`，最后一次合并执行结果为 125 passed。

CLI 全量命令沿用修复记录。Runtime 定向命令为 `pnpm --dir runtime test -- src/core/utils/font-registry.test.ts` 和 `pnpm --dir runtime check`；本机复用依赖时在 pnpm 后增加 `--config.verify-deps-before-run=false`。最终 wheel 也重新装入 `.tmp/review-font-theme-install-20261020`，以 `python -I` 确认从隔离 site-packages 加载下载修复和 Skill 1.4.4。

当前分发候选（替代首轮审查构建的旧摘要）：

| 产物 | 字节数 | SHA256 |
| --- | ---: | --- |
| web_presentation_cli-0.3.5-py3-none-any.whl | 140680 | `3668575092508175B21774AC094FE049173F1924FA6E04318797EA07333ECA8A` |
| web_presentation_cli-0.3.5.tar.gz | 132875 | `A7137F7E2F6CF6450E3FFC5EDC032DA16CBDBBA3B4EA4368E8114D31487B9A0C` |

临时原始证据、测试脚本、PNG 与下载素材位于主仓 `.tmp/web-presentation/font-theme-live/`；安装包在 CLI 仓 `.tmp/review-font-theme-dist/`。认证、带票据的预览响应仅留在忽略目录，不入库、不公开。

## 剩余边界

- 本轮 2026-10-20 尚未启动旧版 Backend 做版本兼容实测。2026-10-25 用户补充确认：当前本机 CLI profile 已连接旧版 Backend，新 CLI 与旧端兼容行为已实测通过；旧端精确版本与命令日志未归档，因此只计入该实际组合，不外推最低支持版本。
- 本轮记录固定的是当时未提交的源码快照。之后主仓 `de5337a`、CLI 仓 `5b2f007` 已提交修复；最终发布前仍须按拟发布提交重建安装包并核对源码、契约与产物摘要。
- 未运行全仓 `test:all`，未声称覆盖所有 Editor/AI/Renderer 专项；未发布 PyPI、推送或部署。
