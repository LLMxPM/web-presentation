# 音频联调与验收计划

状态（2026-10-25）：资源、旁白和 cue 已默认开放。主仓与 CLI 已实现，动画前联合验收已补充 Chromium 实机、独立构建及 cue 长稳证据；本页 A01–A20 是原阶段验收矩阵，尚未逐项全数关闭。真实 M4A/OGG、Firefox/WebKit、部分旁白生命周期与浏览器布局场景仍未覆盖；MCP 已移出当前交付范围。测试命令和环境准备遵循 [`dev-start-test`](../../../../.agents/skills/dev-start-test/SKILL.md)。

[联合验收记录](../../../archive/developer-work-2026-10/pre-motion-joint-acceptance.md)已确认：CLI 上传/下载/替换 WAV，受保护读取 Range/HEAD/304 与拒绝路径，MP3 手动播放及离页停播，旁白与 cue 用户实听、自动播放受阻重试、双窗口观众唯一发声，静态 PDF/PPTX 禁播，以及独立 ZIP 中 30 分 55 秒的 1000 次 interaction cue、1000 次前进 cue、2000 次导航。后者是 cue 长稳；旁白只承诺已实测的播放、恢复和离页停声，不要求 30 分钟循环。后续播放收敛规划在 `feature/motion` 分支接续尚未覆盖的场景。

## 1. 自动化层级

| 层级 | 必测内容 |
| :--- | :--- |
| Backend 单元/API | 枚举、扩展名/MIME、严格音量、cue key、同工作空间/类型校验、引用保护、旧客户端省略语义 |
| 契约 | OpenAPI 生成类型、Runtime Kit manifest、共享正反例、artifact camelCase、模板包往返 |
| Runtime 单元 | AssetAudio props、purpose 收集、generation 清理、media_end、cue pool、节流、静态 no-op、transition started |
| Editor 单元 | 类型选项、accept、试听不自动播、cue 表单映射、错误与清空 |
| Renderer/导出 | 静态上下文不播放、不等待、不泄露票据，PDF/PPTX 报告语义稳定 |
| 真实浏览器 | autoplay blocked、格式播放、Range、页面切换、双窗口、全局静音、快速点击与长稳 |
| 外部消费者 | CLI 上传、查询、绑定、清空、幂等与能力协商；MCP 接入另行规划 |

## 2. M0 验收（A01–A06）

### A01：资源全生命周期

分别上传 MP3、M4A/AAC、OGG、WAV 样例，验证列表、过滤、详情试听、替换、历史、复制、归档、恢复和原始下载。错误扩展名、伪造 MIME、空文件和跨工作空间请求必须拒绝。

### A02：受保护读取

在 Editor 登录态、preview artifact 和独立构建三种路径读取音频；验证 HEAD、Range、304、过期票据、错 workspace/hash 和无凭证。响应 Content-Type 正确，浏览器 seek 不需要下载完整文件。

### A03：`AssetAudio.v1` 内容播放

同页两个 content 音频分别手动播放、暂停、seek 和调速；未命中 name 显示有界 fallback。普通预览不自动播放，组件卸载后无残余监听。

### A04：资源引用与删除保护

页面和工作空间组件通过 `AssetAudio name` 引用时，引用摘要可见；归档/删除按现有规则阻止或提示。动态 name 无法静态收集时继续使用构建额外资源机制，不假装已解析。

### A05：artifact、构建与包

预览和构建都包含音频的 name→hash 映射；构建后关闭 Backend 与外网仍能手动播放。项目模板/组件包导出导入后音频字节 hash 一致，名称冲突和事务失败不留下半包文件。

### A06：M0 静态隔离

thumbnail、截图、PDF、PPTX、打印和 code check 不开始播放、不等待 ended、不弹 autoplay blocked。导出结果不包含私有票据；音频省略报告符合契约。

## 3. M1 验收（A07–A13）

### A07：旁白开始时序

使用 700ms push 和慢图片页面，确认旁白在过渡 settled 且 render-ready 后才开始；快速连续导航时被淘汰 generation 从不发声。

### A08：页面生命周期

旁白播放中执行暂停/恢复、切到后台、freeze/restore、离页、返回和退出全屏。只恢复此前正在播放的当前 generation；离页后归零，返回从头开始，无跨页声音。

### A09：推进模式

- manual：旁白结束不翻页。
- timer：计时到达可中断旁白翻页，Editor 显示短时长警告。
- media_end：旁白与其它参与媒体全部结束后翻页；loop 媒体不阻塞；无媒体按 delay 回退。

### A10：受阻与错误恢复

在无用户手势的新窗口触发浏览器 autoplay 拒绝，确认 UI 可重试并在手势后继续。404、断网、解码失败进入错误/超时路径；用户仍可下一页或停止放映。

### A11：全局静音和音量

项目/组件/会话三层增益计算正确；`M` 和控制条状态一致。静音不暂停时间轴，取消静音继续当前媒体，不把会话静音写回 Backend。

### A12：演讲者唯一播放者

控制台和观众窗口同时打开、重连、刷新和角色降级时，任何时刻只有 audience 发声。控制台关闭不复制播放；audience 接管 generation 后旧窗口停止。

### A13：M1 旁白资源释放

在真实浏览器中验证旁白开始、受阻恢复、离页与退出放映后的停声和资源释放；重复进入与离开时检查 Audio 元素及监听器没有持续增长。此项不设 30 分钟旁白循环或固定翻页次数门槛，长时稳定性按实际支持范围另行记录。

## 4. M2 验收（A14–A20）

### A14：cue 持久化与引用

绑定、替换、清空系统 cue 和自定义 `interaction.*`；拒绝非 audio、归档、跨工作空间和非法 key。音频资产引用摘要列出项目与 cue key，cue 资产自动进入 artifact。

### A15：切页精确触发

前进/后退分别命中正确 cue；初次挂载、同路径刷新、失败导航和被合并的中间导航不发声。快速切页时前一个 transition cue 被替换，不叠加。

### A16：点击 cue

页面按钮显式调用 `useAudioCue.v1` 后才发声；事件冒泡、嵌套按钮、拖拽和 Runtime shell 控件不会被全局捕获。未绑定 key 稳定 no-op，业务动作不等待声音。

### A17：并发与节流

同 key 高频触发受 80ms 节流；不同 interaction 最多 4 路；池满、加载失败或静音时不无限创建 Audio。切页 channel 不被 interaction 池抢占。

### A18：执行上下文

实际放映允许 cue；普通预览只有显式试听；Presenter console、thumbnail、capture、PDF/PPTX/print/check 全部 no-op。`prefers-reduced-motion` 不改变音频契约，但全局静音始终优先。

### A19：配置往返

Backend、Editor、preview/build、模板包、External API 和 CLI 对三段音量及 cue 绑定一致往返。MCP 另行接入，不作为本项完成条件。旧客户端省略字段不清空；显式空列表按契约清空；旧 artifact 不受后续修改影响。

### A20：M2 实机与长稳

独立构建产物完成至少 1000 次 transition cue、1000 次 interaction cue 和 200 次页面导航，确认无持续发声、对象/监听增长或不可恢复的 blocked 状态。Chromium 必测，Firefox/WebKit 记录支持矩阵。

## 5. 证据要求

- 保存 Backend/Editor/Runtime/Renderer/契约测试命令、版本和结果摘要。
- 保存真实浏览器控制台、关键事件时间戳和 network Range 证据；不提交可重新生成的大音频或录屏。
- 音频听感不能只写“人工通过”：至少记录触发次数、start/stop 时间、generation、实际播放窗口和错误状态。
- 模板包、构建产物和导出文件记录 hash、大小和检查结论。
- 涉及 UI 的工作包保留截图；涉及声音的工作包可保留短测试素材的来源/授权说明，测试素材应可合法入库。

## 6. 发布门槛

- 当前资源、`purpose="narration"` 与项目 cue/`useAudioCue.v1` 已默认开放；此处保留原 A01–A20 矩阵作后续补证清单，不再以全矩阵通过作为已开放能力的前置条件。
- 对外文档只声明已验证的 Chromium 场景；M4A/OGG、Firefox/WebKit、长时间旁白循环和其它未测路径不列为已验收。MCP 不作为当前交付门槛。
- 任一阶段若只验证 Chromium，用户文档必须明确浏览器范围；不能用单元测试替代真实媒体策略证据。
