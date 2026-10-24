# C3 联合验收与开放

状态：待实施。主责：跨模块验证。前置：[C2](./c2-legacy-zero.md)、[A2](./a2-support-matrix.md)。出口：GC。

## 交付

- 真实 Chromium 中贯通 Editor、Backend、Runtime、Renderer、CLI 与独立构建产物：播放、退出、翻页、`scene_end`、静态截图、观众窗口唯一调度与演讲者窗口有限意图/原子状态同步。
- 用同一含 DOM 序列、两模型动作、旁白、自动视频、无限装饰与 cue 的页面，覆盖资源替换、媒体受阻与观众窗口本地重试、缓冲、隐藏/恢复、冻结后不连跳、快速切页、`hold/release`、原子状态重复/旧 revision/观众窗口重开对齐与 Renderer 取消。
- 确认生产裁剪镜像的最终发布身份与 preview/check/build 角色，验证独立产物可脱离开发服务器播放与静态导出。
- 至少 30 分钟受控循环，记录 JS 堆、RAF/计时器、媒体元素、WebGL context、canvas、Renderer 进程/槽位，并补 G2-04 要求的 dropped-frame 与 RAF 间隔指标。沿用既有 soak 证据方法：有头运行加全屏透明输入 guard 并以 `noExternalInput` 为通过条件；CDP `Memory.getDOMCounters().jsEventListeners` 用低水位而非首尾中位数；wake lock 结论区分有头与无头（无头返回 `NotAllowedError`）；合成 `freeze` ＋ `pageshow(persisted=true)` 不等于真实操作系统睡眠，须注明未验证。时长若短于旧证据的 61 分钟需说明理由。
- 按 B3 的 renderer 所有权决策给出 A04/G2-06 的修复或接受结论：修复需复测 100 次进出后堆稳定；接受则记录增长曲线、影响边界（文档销毁后释放）与后续计划，不宣称零增长。
- 一次性收口全量主门禁与相关专项门禁，关闭或明确记录中间态积累的已知红项；判定 motion G2 是否可正式关闭。
- 汇总能力、限制、支持矩阵、测试与发布检查表；只有证据齐全才把新模型标为已开放，旧 G2/M2/M3 结果不能代替本次验收。给出 D1 是否启动的结论及依据。

## 验收

按 dev-start-test 选择并运行全量主门禁与相关专项门禁，含真实截图与独立构建；记录实际命令、结果、版本、失败重跑与未覆盖项。不得用单测或开发服务器截图替代真实 Renderer、生产产物与多窗口验证。
