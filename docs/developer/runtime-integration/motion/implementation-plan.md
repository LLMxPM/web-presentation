# 首期编排实施顺序

状态：WP01–WP03、WP07 完成；WP04–WP06、WP08–WP12 待验收，[G0 功能选型通过](./g0-decision.md)，G1/G2 未关闭，能力未开放。采用 GSAP 与受控原生视觉＋资源 builder；公开 Schema/入口待正式化。性能不纳入本轮选择依据，首轮数据保留为历史候选。

## 分阶段交付

| 阶段 | 工作包 | 阶段结果 |
| :--- | :--- | :--- |
| 技术验证 | WP01 | 已完成：样本、GSAP、默认创作形状与最小裁剪交付路径收口，关闭功能 G0；预算后置 |
| 契约与核心 | WP02、WP03 | 有类型约束的定义、共享正反例、确定性计划、虚拟时钟和独占目标注册 |
| 执行适配器 | WP04、WP05、WP06；WP07 维护跨端资产摘要 | DOM、音视频与模型可由同一逻辑位置驱动 |
| 宿主与捕获 | WP08、WP09 | 放映/预览所有权、timeline_end、双窗口、指定状态取帧；关闭 G1 |
| 创作与公开交付 | WP10、WP11 | 统一 Runtime Kit 入口、预览控件、模型指南、External API 与客户端适配 |
| 联合验收 | WP12 | 跨域真实预览、远程 Renderer、独立构建、模型创作基准与兼容矩阵，关闭 G2 |

WP01 已选择 GSAP，原生视觉段落＋有限资源 builder 为单一默认方向。2026-10-21 评审修复已接入正式 Runtime 的 `usePageTimeline.v1`；GSAP 3.15.0 为生产依赖，manifest 入口保持 internal-only。Anime.js/Motion/WAAPI 的研究材料保留，不并行实施多套主引擎。实现不等于 G1/G2 验收通过。

## 模块边界

| 模块 | 负责 | 不能承担 |
| :--- | :--- | :--- |
| Backend | 能力门禁、资源与动作摘要、放映配置、捕获选择器、任务/指纹/发布围栏 | 执行 Vue、启动浏览器、按正则猜任意 TypeScript 的完整编排 |
| Runtime core/motion | 计划编译、逻辑位置、状态、目标所有权、适配器和采样 | 私有文件鉴权、业务数据库、任意业务回调系统 |
| Runtime Kit | 版本化创作入口、类型与受控资源句柄 | shell 控制条、完整场景编辑器、Three.js 私有对象透出 |
| Runtime shell | 放映生命周期、预览操作、观众唯一播放者和错误恢复 | 复制轨道解析器、直接控制已由时间轴认领的元素 |
| Renderer | 在受信浏览器解析定义、应用选择器、确认帧、捕获与取消清理 | 修改业务对象、把图片失败覆盖已完成的诊断 |
| render-contracts | 远程捕获 DTO、Schema、版本、就绪回执和错误词汇 | 页面编排业务执行器或 HTTP 客户端 |
| Editor | 预览控制与状态、timeline_end 表单、查询返回的动作摘要 | 首期图形时间轴、另一份时间轴持久化数据 |
| CLI/MCP | 消费标准 External API、能力查询、参数透传、版本失败提示 | 直连 Runtime/Renderer、忽略不支持字段后伪成功 |

## 代码落点

新增目录名为实施默认方案，实际拆分可随代码边界调整：

- `runtime/src/core/motion/`：definition/plan 编译、transport、clock、target-registry、sampler 与适配器，保持纯算法和 Vue/DOM 绑定分离。
- `runtime/src/runtime-kit/internal/renderers/model3d/motion/`：每实例 mixer、clip 采样、整体包装变换和资源释放；从现有 ModelViewer 抽出相关职责。
- `runtime/src/runtime-kit/manifest/schemas/`：创作 Schema 与公开能力说明；生成类型与正反例由 WP02 维护。
- `backend/app/services/`：资源动作分析、快照身份与捕获任务适配；请求 DTO 仍在 schemas，路由只处理入参和权限。
- `tests/fixtures/`：正反例、短媒体与自包含模型样本、预期采样位置；大型设计源文件不入库，可重建样本提供生成说明。

新 Python 依赖、导入和浏览器工作继续遵守根 AGENTS；变更 HTTP DTO 后执行 Editor codegen 和生成漂移检查。涉及放映 schema 3、模板包与 Remote Render v2 的修改要联动双端解析和往返测试。

## 热点文件与集成顺序

- WP02 维护创作 Schema、规范类型和错误词汇；WP04–WP06 只实现适配器，不各自扩展语法。
- WP07 维护 Backend 动作摘要、能力结构和生成类型；旧能力是否已开放依据当前注册表，不根据历史计划的勾选状态推断。
- WP08 维护 usePlaybackHost、ExecutionPolicy、PageMediaSession 所有权桥接、slideshow Schema 与 presenter v4；其它包通过接口接入。
- WP09 维护 render-contracts v2、render-ready、OffscreenPageStage、默认截图发布与静态模型帧身份。
- WP10 维护公共 composable、Asset*.v2 及 Editor 预览交互；旧 v1 的可见行为要有回归。
- WP11 消费已冻结的能力与 DTO，联动独立 CLI/MCP 仓；不在客户端另维护工具目录或动画库 API 镜像。

适配器可以在共同输入完成后独立评审；工作包依赖表示代码实施关系，不自动创建或派发多个智能体任务。

## 数据与兼容

首期不新增时间轴表，不把运行位置写入数据库。现有页面/组件版本保存源码，项目/路由保存新的明确推进方式。新增能力关闭时，后端拒绝 timeline_end 写入，Runtime Kit 不向普通创作流披露可执行新入口。

开发阶段使用专用测试工作空间和 _e2e 库；不批量改写用户现有页面、模型或放映配置。动作摘要升级需要有界、可重试的补算方式，不能在读取资源列表时同步解码整个 GLB。

变更影响文件身份、检查输入和产物发布时复用现有 hash、attempt 与写围栏。资源替换、取消和迟到回执应覆盖到真实任务链路，不建立编排专用的第二套截图队列。

## 发布顺序与回退

1. 先部署能够同时读取旧契约与新契约的 Backend、Renderer 和 Runtime，能力保持关闭。
2. 内部样例完成 G1；Editor、CLI/MCP 与生成类型就绪后完成 G2。
3. 只向匹配版本的预览/渲染副本派发新请求，随后开放能力标记与文档。混版池不能把新选择器派给 v1 Worker。
4. 回退时先停止新写入和新会话，排空使用新版本的任务，再撤下新执行器；已经保存 timeline_end 或新 Runtime Kit 引用的内容不能降级成旧接口继续宣称可用。

能力关闭不等于删除新定义；保留诊断与显式“不支持”状态。不得把旧请求默默转换成另一帧，也不得通过 public fallback 绕过资源鉴权。

## 交付记录

测试命令和本地服务操作统一引用 [dev-start-test](../../../../.agents/skills/dev-start-test/SKILL.md)。工作包记录具体选择、命令、结果和证据；本页不复制 E2E 启停脚本。

初次规划记录保留在[验收计划](./acceptance.md)，WP01/G0 的最终结论与证据见[G0 决定](./g0-decision.md)；第一轮数据保留为历史，G1/G2 尚未执行。

## 设计参照

首期采用“轨道定义、目标绑定、统一控制、分介质执行和确定状态采样”的组合。以下资料用于界定候选机制，不代替 G0 实测：

- [GSAP Timeline](https://gsap.com/docs/v3/GSAP/Timeline/)：已选视觉引擎的标签、嵌套、相对位置与整体控制；正式依赖待实现阶段加入。
- [Web Animations](https://www.w3.org/TR/web-animations-1/)：原生动画时间与定位，保留底层参照；此前已定结论撤回。四候选资料与当前判断统一见选型补充。
- [Remotion buffer state](https://www.remotion.dev/docs/player/buffer-state)：把播放意图与缓冲状态分别处理。
- [Three.js AnimationMixer](https://threejs.org/docs/pages/AnimationMixer) 与 [AnimationAction](https://threejs.org/docs/pages/AnimationAction.html)：模型片段执行、定位、循环和结束状态。
- [HTML 媒体规范](https://html.spec.whatwg.org/multipage/media.html#seeking)：媒体定位的异步行为；[Web Audio](https://www.w3.org/TR/webaudio-1.1/#dom-baseaudiocontext-currenttime) 说明音频自己的时间坐标，后续精细混音需单独评估。
