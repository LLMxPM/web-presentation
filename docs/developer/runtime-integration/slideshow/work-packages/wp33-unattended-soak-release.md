# WP33：本地放映长稳演练与证据门槛

状态：已完成（2026-10-18）。阶段：M3。主责：跨模块验证 / 运维。
上层工作项：R06（长稳）、M3 出口；详见[模块计划](../acceptance.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP31](./wp31-unattended-entry.md)、[WP32](./wp32-unattended-recovery.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：在 WP31 的本地构建产物入口上执行至少 60 分钟多页循环；记录内存、媒体句柄、计时器、监听器、wake lock 与浏览器进程状态，并复现 WP32 的休眠/唤醒和本地服务中断恢复。远端部署、构建访问票据/代理和发布流程不进入本包。
- 交付物：限定设备、浏览器和本地服务形态的长稳报告与支持边界，关闭 M3 验收清单。
- 提交边界：只在证据覆盖范围内声明本地验证结果；不将一次演练等同于所有设备全天承诺，不据此开放产品级无人值守、远端构建访问或公开发布能力。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：循环无持续资源增长、旧事件推进或重复调度；休眠/唤醒与本地服务中断按 WP32 结论可解释；未通过项明确列出，不能以短时单测替代。
- [x] 验证范围：至少 60 分钟多页循环、浏览器和本地静态服务的恢复演练、适用的发布主门禁；记录代码版本与设备矩阵。
- [x] 关联验收：M3 专项：60 分钟长稳与支持矩阵；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP33：本地放映长稳演练与证据门槛`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录（2026-10-18）

- 代码与产物：代码提交 `20e7f0e`；构建任务 13 的 ZIP SHA-256 `73580772e85a0f75aa3f783f9ae2b4c7b0c5894d6fd2285ead8d6eadb12807de`，大小 15,448,159 字节；本地静态服务 `127.0.0.1:7417`；有头 Chromium 148.0.7778.96（Playwright 1.60.0），Windows 10.0.26300 x64，1280×720；4 页可见页面，timer 5s + `media_end` 短视频 + 循环/自动开始。
- 长稳：连续 61.08 分钟、61 次采样（60s 间隔）；553 次自动翻页（`/intro` 138、`/content` 139、`/media` 139、`/closing` 137，约 138 轮），顺序为 intro→content→media→closing→intro，无短于 2s 的连跳；外部页面点击/按键 0（输入拦截与记录）。
- 资源：JS 堆中位数 8.4→8.4MB；浏览器进程树 RSS 704.2→703.5MB；DOM 139–141；CDP 监听器低水位 66→66（峰值 184，锯齿回落，无持续增长）；活动计时器最大 3；媒体元素最大 2；无页面崩溃、无浏览器断连、无意外控制台错误或失败请求。
- 防休眠：稳定放映样本 Screen Wake Lock `active` 100%；申请次数峰值 4（启动、显式继续与重载后的重新申请，重载时计数重置）；暂停、隐藏、冻结、结束和清理均释放。
- 恢复演练：I1 隐藏 15s 后暂停且锁 `idle`，15s 内不翻页，可见后保持暂停，显式继续恢复；I2 注入 `freeze` 后暂停、20s 内不翻页，持久化 `pageshow` 保持暂停，显式继续恢复；I3 停止本地服务后媒体请求 `net::ERR_CONNECTION_REFUSED`，进入错误态且 3s 内不跳页，重启服务后点击重试 1029ms 恢复播放；I4 浏览器重载从 `#/intro` 自动开始并持有屏幕锁。
- 检查结果：duration、sampleCount、automaticTransitions、transitionOrder、noShortIntervals、domBounded、listenersBounded、noExternalInput、timersBounded、mediaBounded、wakeLockHeld、wakeRequestsBounded、heapBounded、processRssBounded、noUnexpectedConsoleErrors、noUnexpectedFailedRequests、wakeLockReleasedOnCleanup、mediaPausedOnCleanup、noPageCrash、browserConnected、allRecoveryEvents 全部通过，`failures=[]`。
- 首轮演练：同样完成 61 分钟资源采样，但在第 20 分钟冻结窗口出现“已停止”与 0.5–0.9s 快速连跳，判定为外部点击/按键干扰，未采信；加入全屏输入拦截与点击/按键记录（`noExternalInput`）后重跑，最终以上述第二轮证据为准。首轮证据保留在 `.tmp/wp33/soak/failed-61min-*`。
- 证据与命令：`node .tmp/wp33/soak.mjs`（最终）、`WP33_FAST=1 node .tmp/wp33/soak.mjs`（流程校验）；结果在 `.tmp/wp33/soak/evidence.json`、`run-output.txt` 和 I1–I4 截图；WP32 证据在 `.tmp/wp32/browser/`，WP31 证据在 `.tmp/wp31/`。适用的 Runtime 门禁为 142 files/1105 passed/3 skipped、`check`、`build` 与改动文件 ESLint；未运行主全量 E2E（会停止共享开发服务，且本阶段不开放产品能力）。
- 未运行：真实操作系统睡眠/唤醒、Firefox/WebKit、移动端行内播放、注入式 renderer 崩溃、远端构建访问代理与发布流程；一次演练不等于所有设备全天承诺。
- 清理：专属用户（11）、工作空间（40）、项目（124）、构建任务 11–13、发布/页面/资源数据行、对象目录 `backend/data/assets/40` 与 `backend/data/build-artifacts/124` 已删除，3 个构建产物通过鉴权接口返回 204；`.tmp/wp31/account.json` 已抹除，剩余计数为 0，见 `.tmp/wp31/cleanup.json`。

## 支持边界（演练矩阵）

| 维度 | 本次验证范围 | 未验证 / 不承诺 |
| :--- | :--- | :--- |
| 设备 | Windows 10.0.26300 x64 桌面 | 移动端、其他操作系统 |
| 浏览器 | Playwright 1.60.0 有头 Chromium，1280×720 | Firefox/WebKit、旧版本浏览器 |
| 放映来源 | 真实构建任务 ZIP，本地解压 + 本机静态服务 | 预览 artifact、Runtime 开发服务器、远端构建访问代理 |
| 本地服务 | `127.0.0.1` 静态文件服务，可停止/重启 | 远端网络、鉴权代理、CDN、跨机部署 |
| 配置 | 4 页可见页面，timer 5s + `media_end` 短视频 + 循环/自动开始 | 其他媒体格式、复杂页面、演讲者模式和远程控制 |
| 时长与承诺 | 单次 61 分钟演练（含中断恢复） | 24 小时、全天候或所有设备无人值守承诺 |
| 防休眠 | Screen Wake Lock 获得与 `NotAllowedError` 回退 | 所有设备/权限策略、真实操作系统睡眠 |
| 恢复 | 隐藏、`freeze`/`pageshow`、本地服务中断重试、浏览器重载 | 注入式 renderer 崩溃、远端代理故障 |

单次演练只覆盖上述组合，不据此开放产品级无人值守、远端构建访问或公开发布能力。

## 全屏放映统一模型后的证据口径（2026-10-18）

- 上述 61 分钟长稳在统一模型之前的窗口化入口执行：直接打开构建链接后由 `auto_start` 在窗口内自动推进。该结论继续证明控制器计时、媒体会话、循环、防休眠、清理与恢复链路的长稳，但不等于全屏入口证据。
- 统一模型后进入放映需要用户在 Runtime 窗口点击全屏；退出全屏即停止。全屏会话的握手、控制条与演讲协议 v3 已通过 Runtime 自动化测试和本轮真实浏览器交互检查，尚未重新累计 60 分钟全屏无人值守。
- 支持矩阵中的“演讲者模式”未纳入本卡长稳；观众窗口全屏门禁、唯一调度和模式继承需在后续专项或 M3 补充演练中记录。产品级远端无人值守仍不在已开放范围。
