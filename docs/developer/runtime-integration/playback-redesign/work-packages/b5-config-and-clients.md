# B5 配置与调用端收敛

状态：**工程完成（2026-10-31），实机待 C3**。主责：Backend / Editor / AI / CLI。前置：[B2](./b2-completion-aggregation.md)。B0–B5 工程出口 GB 已完成；旧内核清零与最终交付验收仍由 C2/C3 收口。

## 已交付

| 范围 | 结果 |
| --- | --- |
| 配置与快照 | Backend/Editor/Runtime 同批切换 slideshow schema 4：manual/timer/scene_end、定时停留、完成后停留与 loop；删除自动开始、旧模式和超时。模板包 schema 5，旧包明确拒绝。 |
| 读入边界 | API 严格类型与权限；旧持久化配置 409 SLIDESHOW_CONFIG_UNSUPPORTED；预加载/外部配置及构建/诊断拒绝旧版本，RUNTIME_SLIDESHOW_SCHEMA_UNSUPPORTED。旧 artifact 需要重建，不做兼容映射。迁移只改新行默认，未操作开发库。 |
| Editor | 生成 DTO、项目/逐路由/批量共享字段；允许零完成停留，保留整组覆盖和 null 继承，移除自动开始与旧超时。预览仍只有播放/停止，放映用保持/释放，不提供页内暂停或定位。 |
| Presenter v5 | request-state、有限 intent、原子 state；观众唯一调度，按 owner/revision 拒绝乱序与旧窗口，新 owner 接管停止旧窗口。删除时间位置、倒计时、ack/重放、旧 v4 和会话自动切换。控制台 interactive-preview，小窗 thumbnail。 |
| 媒体许可 | 观众本地播放/重试、静音与许可提示；控制台点击不替代观众手势，全屏不保证发声。删除无消费者的 allowPresenterSync 标志。 |
| AI 与样例 | tool_specs 单一规格、派生目录/手册/披露与页/组件规范统一 Scene、模型 v3、显式媒体、cue v2 和独立静态态；禁止 GSAP 插件，粒子用 DOM/CSS/Canvas。联合样例包含数字、打字机、SVG、粒子、两个真实模型动作、旁白与 cue，按真实索引/签名和 ended 完成。 |
| CLI | 相邻仓库 CLI 0.4.1 / Skill 1.4.7；严格 schema 4、无音频阶段门禁、删除时间点截图参数。独立静态任务支持 --job/--no-wait/--job-id，区分 ready/pending/unavailable/skipped/failed，固定同源内容端点，保留原因码。 |

主仓实现提交：`080e221` 配置/表单、`ae7f4f6` Presenter、`299708d` AI/样例。CLI 功能提交：`9f13ca5`，版本修正：`d8a4d27`，分支 feature/motion-scene-clients；仅本地提交，未发布。详细过程见[开发记录](../development-record.md)，现行规则见[放映契约](../../slideshow/contract.md)与[Scene 指南](../../../runtime/scene-development.md)。

联合样例的可选 modelName/narrationName 必须来自真实工作空间资源，模型至少有两个真实已签名片段；不足时失败，不猜测片段。开发回归使用真实 Mixer 和原生媒体事件替身，未取得 WebGL、声音或真实创作通过证据。样例发现并修复了顺序片段之间残留 clamp 权重导致姿态平均的问题。

## 开发验证

- Backend 配置/继承/权限/快照/模板/渲染身份定向回归通过；配置批次 73 项、补充集合 49 项通过及 1 项既有跳过。AI 工具/目录/业务集成 39 项，Kit/CLI Skill 10 项通过。
- SQLite 实际默认值升降级、既有 JSON 保留与 PostgreSQL 离线 DDL 通过；未执行真实 PostgreSQL 或开发库升级。
- 完整 Runtime：185 文件 1461 项通过、3 项既有跳过；Presenter/Deck/策略/布局 79 项、样例/模型/核心入口 21 项定向通过。Runtime check/build 通过。
- 完整 Editor：160 文件 904 项通过；check/build 通过。根仓 20 文件 129 项契约、codegen 与生成门禁、Gateway 通过。E2E 仅 --list 收集校验，未运行浏览器。
- CLI 完整 API Client/CLI：209 项通过，无跳过；最终截图/放映/音频边界集合 45 项通过（含新增 3 个任务身份/版本负例）。实时生成主仓 OpenAPI 对拍、help、lock --check --offline、wheel/sdist、Skill 分发与 quick_validate 通过。产物在 CLI .tmp/dist-0.4.1，未发布。

## 交接与非阻塞事项

- [C1](./c1-static-capture.md)：最终截图、诊断附图、Renderer 取消/清理和静态契约收口。本包未修改截图 DTO。
- [C2](./c2-legacy-zero.md)：清除剩余旧编译器、Transport、采样和 usePageTimeline 公开入口。开发分支暂存旧入口不代表已通过合并 main 门禁；正式调用端已切换，不增加 fallback。
- [C3](./c3-acceptance-release.md)：真实助手 + Editor + CLI 创作、Mutation Job → Renderer、截图/导出、独立产物、正式多窗口、播放许可、发声、WebGL、后台节流、长稳和全量门禁。PresenterPageGrid 仍每页一棵真实 Vue 树；实际页数上限与卡顿边界留 C3 测量，本包未声称已有性能上限。
- MCP 不在本次交付链。External capabilities 的 timeline → scene、放映 schema 4 和模板 schema 5 会使其旧快照/bindings 失配；本次未刷新、未执行 MCP 测试，明确记录为非阻塞，不作为 GB 或主仓/CLI 验收条件。

版本号按用户要求采用补丁版本；Skill 兼容范围为 `>=0.4.1,<0.5.0`。版本与 Skill 管理 37 项定向回归、离线锁文件、wheel/sdist 和分发验证通过；本次未重跑业务全量或实机测试。
