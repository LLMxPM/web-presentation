# 放映动画能力收敛工作包清单

状态：**A1–C3 待实施，D1–D3 推迟**。本清单执行[放映动画能力收敛规划](../../playback-redesign-proposal.md)；放映优先，永久放弃任意时刻状态重建，无历史发布数据，不安排旧接口兼容、存量页面迁移或双版本混跑。工作包编号与旧 motion/slideshow/audio/threejs 的编号无关。

取代 2026-10-23 的 WP01–WP16 十六包草案。收敛要点：先用现有能力贯通一次真实放映（A 段）；B0 先让默认截图与静态导出脱离时间轴采样，再删除指定时刻截图并切换正向播放（B 段）；最后复验静态链路与发布（C 段）。**不新建第二套播放内核，不推倒重做。**

## 三段与出口

| 出口 | 必需工作包 | 证明什么 |
| :--- | :--- | :--- |
| GA 真实放映可用 | A1、A2 | 四条线在同一个真实放映里贯通跑完；生产镜像可重建；支持矩阵与真实缺口清单确定。等价于 motion G2 关闭条件的重排。 |
| GB 内核收敛 | B0–B5 | 静态态已替代默认时间轴海报；任意时刻重建链已删；完成聚合取代统一时钟；三维、音频、配置与调用端一致。 |
| GC 交付开放 | C1–C3 | 静态结果与不可呈现语义跨产物复验；旧链路清零；真实浏览器、独立产物、长稳与全量门禁证据齐全。 |

推迟项 D1–D3 见[推迟候选](./deferred-candidates.md)，不阻塞 GC。

## 工作包和依赖

| 工作包 | 主责 | 前置 | 可评审交付 |
| :--- | :--- | :--- | :--- |
| [A1 真实放映联合贯通](./a1-joint-playback.md) | 跨模块验证 | 无 | 一次真实放映、生产镜像、Renderer 取消、缺口清单 |
| [A2 支持矩阵与降级边界](./a2-support-matrix.md) | Runtime / 跨模块验证 | A1 | 明确支持与不支持的环境、降级路径 |
| [B0 静态呈现契约与默认截图替代](./b0-static-presentation.md) | Runtime / Renderer / Backend | A1 | 默认 PNG/附图/导出脱离时间轴采样；静态结果与不可呈现语义冻结 |
| [B1 删除指定时刻截图协议](./b1-drop-arbitrary-moment.md) | Runtime / Backend / render-contracts | B0 | `motion_snapshot` 与对外选择器删除；旧正向播放调用点暂留 |
| [B2 完成聚合取代统一时钟](./b2-completion-aggregation.md) | Runtime core / shell | B1 | `usePageScene.v1`、generation、`scene_end`；旧编译器/Transport/采样调用点同批删除 |
| [B3 三维正向片段播放](./b3-model-forward-playback.md) | Runtime model3d | B2 | ModelViewer 拆分、renderer 所有权、实例 Mixer |
| [B4 音频所有权统一](./b4-audio-ownership.md) | Runtime media | B2 | AudioBus、三类所有权、媒体用途声明 |
| [B5 配置与调用端收敛](./b5-config-and-clients.md) | Backend / Editor / AI / CLI | B2 | 新放映 DTO、最小意图与原子状态协议、AI 指引、CLI |
| [C1 静态捕获跨产物复验](./c1-static-capture.md) | Runtime / Renderer / render-contracts | B3、B4、B5 | PNG/缩略图/PDF/PPTX 静态一致性、不可呈现语义与截图身份复验 |
| [C2 旧链路清零与文档](./c2-legacy-zero.md) | 跨模块 | B5、C1 | 无旧入口残留、生成物与文档一致 |
| [C3 联合验收与开放](./c3-acceptance-release.md) | 跨模块验证 | C2、A2 | 浏览器、独立产物、长稳、A04 结论、全量门禁 |

B0 是 B1 删除默认海报采样依赖的硬前置；B1 只移除未开放的外部截图选择器，旧播放内部编译器直到 B2 新会话接管才删除。B3、B4、B5 在 B2 完成后可并行；三者分别独占 model3d、media 与配置/调用端，避免同时改同一批文件。B5 中 Backend 放映 DTO 与 Editor 配置表单必须同批落地——DTO 重定义并重新生成类型后，旧表单引用立即失效。C1 独占最终截图与 Renderer 契约复验，B5 不修改截图 DTO。

## 旧未闭环项处置

四条线的未闭环项逐项归属如下；来源见[motion G2 遗留清单](../../motion/g2-followups.md)与[规划第 2 节](../../playback-redesign-proposal.md)的资产盘点。

| 旧未闭环项 | 来源 | 处置 | 承接位置 |
| :--- | :--- | :--- | :--- |
| 内置助手 + Editor + CLI 联合创作 | G2-01（P0） | 承接 | A1 |
| 生产依赖裁剪镜像重建 | G2-02（P0） | 承接 | A1 重建并验证三角色，C3 确认最终发布身份 |
| audio WP06/WP12 真机验收、WP20 联调 | audio M1/M2 | 承接 | A1 |
| Renderer 取消清理与槽位释放 | G2-09（P1） | 承接 | A1 |
| 受保护媒体网络缓冲 | G2-11（P2） | 承接 | A2 复现，B4 在新所有权下复验 |
| WebGL 上下文丢失/恢复 | G2-07（P2） | 承接 | A2 演练，B3 拆分后复验 |
| 多窗口降级与后台节流 | G2-08（P2） | 承接并缩小 | A2 演练现有 v4 真实边界，B5 收敛为最小意图与原子状态后复验 |
| 多屏授权、Firefox/WebKit、移动端 | slideshow M3 边界 | 承接 | A2 验证或明确写入支持矩阵为不支持 |
| 修正版 30 分钟长稳 + dropped-frame | G2-04（P0） | 承接并补方法与指标 | C3 |
| A04 渲染器保留 | G2-06（P1） | 承接并前置决策 | B3 决定 renderer 所有权，C3 给出修复或接受结论 |
| 混版与回退矩阵 | G2-03（P0） | 作废 | 无历史发布数据；回退方式为 revert 提交 |
| B01–B08 模型创作基准 | G2-05（P1） | 作废并降级 | B5 与 C3 只要求一个真实端到端样例，不保留 7/8 量化门槛 |
| 组件独立轨道片段预览 | G2-10（P2） | 作废 | 首轮工作空间组件不纳入 Scene；组件动效走 D1 |
| 指定状态截图 | motion（从未开放） | 永久放弃 | B0 替代默认海报采样；B1 删除外部协议；B2 删除播放内部采样链 |

## 完成记录和验证

状态使用“待实施 → 实施中 → 待验收 → 完成”。每张卡片完成时回填代码版本、实际命令、通过/失败数量、浏览器或产物证据、未运行项和接手条件。按[dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)选择最小充分测试；涉及服务、E2E 或全量门禁时先复用运行中的服务。

直接替换期间 dev 允许全量门禁不绿：A 段不改内核，应当保持门禁可用；B 段起旧链路逐步退出，每包只要求本包测试与生成门禁通过，并在卡片中记录未运行项和当时的已知红项；B0/B1/B2 每个出口必须保持默认 PNG 与静态导出可用，不能把截图中断记为已知红项留待 C3。全量主门禁与专项门禁统一在 C3 收口，中间态不为通过门禁补兼容层或运行时 fallback。

新增源码遵守根仓中文注释与文件头要求；Editor UI 遵守 `DESIGN.md`。HTTP DTO 改动须生成 Editor API 类型并通过生成契约门禁，RenderContracts 的 Python DTO 与 JSON Schema 必须对拍。Runtime Kit 的新公开路径须带 `.vN` 并进入 manifest。跨仓 CLI 在其仓库提交与验证，本仓只维护 External API 契约和对接记录；MCP 不在交付链，但 External API 变化会使其契约快照失配，按 B5 记录为非阻塞。
