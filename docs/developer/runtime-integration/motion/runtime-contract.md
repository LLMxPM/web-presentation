# 首期编排运行与捕获契约

状态：拟实施；[G0 已选择 GSAP](./g0-decision.md)与受控原生视觉＋资源 builder。创作方向见[创作契约](./authoring-contract.md)，正式 Schema 由 WP02 定义。性能/规模阈值后置复核，不把首轮历史数值视为已冻结输入。本契约不改变现有未注册页面行为。

## 计划与状态

规范化计划包含 schemaVersion、timelineId、planDigest、绝对轨道区间、目标类型、有限 durationMs、主时钟区间、poster 与 required 集合。摘要进入诊断，完整目标句柄和私有资源地址不进入模型返回。

播放意图为 `stopped/playing/paused`；运行阶段独立为 `preparing/ready/seeking/buffering/blocked/completed/error/disposed`。只有 playing 且阶段允许时才推进。缓冲结束不恢复用户暂停；运行失败不被后续 ready 覆盖。

会话绑定 `pagePath + generation`；定位另有递增 revision。异步资源加载、play Promise、seek 和视频帧回执都核对会话与 revision，旧回执只清理自己，不提交状态。

- `play`：准备目标、取得运行许可并从当前 position 开始；浏览器播放拒绝进入 blocked。
- `pause/resume`：保留位置，恢复前检查用户意图、策略和当前会话。
- `restart`：取消旧尝试、清空完成集合，回到 0 后按显式命令播放。
- `seek`：返回 Promise；在 [0,durationMs] 内取目标时间，默认保持原播放意图；不得补触发跨过的声音或业务事件。
- `dispose`：幂等注销全部目标、计时、监听、待执行操作和 GPU 播放申请，不恢复已销毁页面的媒体。

## 时钟与时间映射

无主媒体时使用单调时钟。媒体主区间内由实际主媒体播放位置换算逻辑时间；播放开始、buffering、blocked 和恢复都必须确认真实媒体状态。

```text
sourceTimeMs = inMs + (timelineTimeMs - trackStartMs) * rate
trackDurationMs = (outMs - inMs) * repeat / rate
```

主媒体必须从逻辑 0 开始且只播放一次。其结束时，先确认结束帧与逻辑边界，再在同一会话无缝换成单调时钟推进剩余 required 轨道；媒体出错不触发这个正常交接。seek 到主媒体之后直接按规范计划采样，不重播主媒体。

实时跟随不逐帧写 currentTime。首轮校正/定位候选阈值保留在[历史记录](./wp01-results.md)，待编排路线确定后复核；本轮不冻结数值。视频漂移应依据 rVFC 的实际帧与预计呈现时刻衡量，不能只比较两个 currentTime。停止更新不能造成后台积累补跳。同步媒体进度经过统一控制器，独立内容媒体保留自己的控件。

Three.js 和 DOM 执行器按逻辑时间应用状态。任意顺序 seek 到 t 都需重建同一状态，不能依赖此前触发过 finished 或 animationend；三维片段每次采样必须明确 action 时间、权重、循环和结束姿态。

## 媒体与所有权

目标注册表发放与 generation 绑定的独占所有权。时间轴认领的媒体不再由 PageMediaSession 自动播放、归零或重复计入完成集合；现有媒体守卫始终作为策略上限，不能被认领绕过。

required 媒体的等待进入 buffering，并暂停同步集合；optional 轨道按冻结/跳过策略告警，不争夺主时钟。所有等待都受一次准备/定位期限约束；取消与超时释放自己的申请，不能无限等待 metadata、canplay 或帧回执。

旁白继续检查现有 narration capability、用途、数量与循环约束。短 cue 的 channel/pool 保持原实现；seek、capture、export、thumbnail 不产生声音。项目 BGM 和跨页音频所有权不在首期交付。

## 宿主和执行策略

| 宿主 | 行为 |
| :--- | :--- |
| Editor 实时预览 | 默认静态 poster，用户显式播放后启动页内时间轴，不自动翻页；提供暂停、重播与定位 |
| 全屏放映 | 资源就绪并且整页过渡 settled 后启动；暂停、离页、后台与退出全屏统一管理 |
| 演讲者模式 | 观众窗口唯一播放器；控制台只发命令和显示摘要，小窗不播放媒体 |
| thumbnail/check | 使用默认 poster，无播放循环、无音频；检查明确针对一个确定状态 |
| capture/export | 以选择器应用状态并固化，只允许解码、定位与单帧绘制，不启动自动播放 |

现有 ExecutionPolicy 的父级上限继续生效。新增动态预览许可只在显式用户操作的当前预览作用域生效；页面不能通过查询参数或源码把静态捕获改成放映。

`system/reduced/full` 是宿主视觉策略输入，system 根据真实环境解析为 reduced/full。运行控制、音频静音与捕获选择器独立处理。预览 full 只来自用户显式选择；普通源码不能忽略系统偏好。首期 reduced 将 enter 直接应用可读终态、模型/变换应用 reducedState；文本标记与旁白仍跟随逻辑时间。关闭视觉运动不能直接触发翻页完成，简化动画映射留待后续。

## 翻页与双窗口

首期新增显式 `advance.mode=timeline_end`，不用 media_end 代指动画结束。它等待 required 有限轨道完成，忽略可选装饰循环；结束事件按 generation 只消费一次。

- 没有合法时间轴时给出契约错误，不静默退为 timer。
- 新增 `timeline_timeout_ms`，默认 300000，范围沿用 1000–3600000；为实际播放时间预算，用户暂停、后台等待和 buffering 不推进该预算，buffering 另受恢复期限约束。
- manual、timer、media_end 保持原语义。timer 仍按既有停留时长推进；若短于编排总长应提示，不擅自延长。media_end 不等待未登记为媒体的动画；需要完整编排后翻页时使用 timeline_end。
- 当前页切换后旧会话立即失效，重新进入从 0 开始；首期不做跨页连续定位。
- 演讲同步消息增加 timelineId、planDigest、positionMs、播放意图、运行阶段、revision 与命令 ID。跨窗口不直接比较 performance.now，不建立第二个时钟；重复、旧 owner 与旧 revision 命令被丢弃。

## 捕获选择与固化

拟新增 `motionSnapshot`，形状为 `{timelineId, atMs, visualMode?}` 或 `{timelineId, atLabel, offsetMs?, visualMode?}`，两者互斥。visualMode 为 full/reduced，默认 full，表示采样哪种视觉映射，不授予播放许可。默认请求使用页面定义的 poster。已有页面没有时间轴时保持当前静态行为。

捕获仍保留原生 reduce 环境用于未托管内容；已注册目标由静态采样器按 visualMode 应用状态，不通过修改系统/浏览器偏好实现取帧。这样可取得完整动效在 t 的静止画面，同时保持全程无声音、无自动推进。

同一个选择器贯穿 Backend 请求、render-contracts、Renderer、Runtime 就绪回执和导出舞台。Backend 可验证形状与边界，标签存在性和真实计划语义由 Runtime 复核。默认发布截图始终使用默认 poster；临时指定时刻截图不覆盖页面默认截图指针。

静态执行顺序固定：

1. 解析并校验计划，准备模型、字体及 required 媒体。
2. 进入无事件副作用的 sample 模式，确定目标时间和视觉偏好映射。
3. 媒体完成 seek，视频确认目标帧就绪；模型更新骨骼、矩阵和包装变换后显式绘制。
4. 固化注册目标的 DOM 样式与模型帧，再退出其原生动画对象影响。
5. 输出包含 planDigest、sampledTimeMs、stateDigest 的就绪回执；捕获端核对本次请求后截图。
6. 清理舞台、覆盖图和申请，不改变主放映的页面、时间、声音或用户偏好。

DOM 引擎待选，属性作用在独立包装层。首轮 WAAPI 样例通过保持合成条件、commitStyles/cancel 和恢复临时 will-change 实现指定状态固化；这是该候选的可行路径，不是其它引擎的接口要求。后续按所选引擎验证固化，不能将取消对象本身当成完成。

不能只调用 animations=disabled 就声称取得指定帧；保留该兜底时必须证明它不会重写已固化状态。默认 poster 解析、timeline_end 最终状态与 reduced 的视觉映射是不同输入，不相互猜测。

媒体不能定位、片段不存在或状态未应用时返回明确失败；optional 资源可返回 degraded 摘要。新时间轴页面无法验证取帧时不能发布一张其它时刻的“成功截图”。附带截图失败仍不覆盖已完成的独立诊断结果。

## 身份与缓存

截图、检查及模型静态帧身份增加实际影响结果的输入：规范计划/源码摘要、选定时间、视觉偏好规则版本、动作资源文件身份与片段、结束姿态、整体变换、相机和实际渲染配置。相同 URL 的不同动作时间不能命中同一模型静态帧。

主时钟墙上时间、用户操作历史、会话 ID 和监听器状态不进入静态像素身份。路由身份仍按已有 page_render_identity 门控规则加入，不将 playback/advance 全量混入。默认海报改变时使默认截图失效；临时 sample 使用独立请求身份。

## 版本与能力

| 边界 | 首期迁移目标 |
| :--- | :--- |
| Runtime Kit | 新增 usePageTimeline.v1 与三个 Asset*.v2，旧 v1 保留 |
| 创作定义 | page-timeline.v1 与 Schema/TS 共用用例 |
| 放映 capability | schema_version 从 2 升为 3，声明 timeline_end；写入门禁随 G2 开放 |
| 演讲协议 | v3 升到 v4，新命令不发给旧协议观众 |
| Renderer | internal/render/v2 与 render-ready.v2 承载选择器和状态回执；v1 请求路径继续支持无选择器旧请求 |
| 能力自省 | 拟增加 `timeline` 分组：schema_version、enabled、track_types、capture_snapshot、advance_modes；false 时不得宣称可执行 |

render-contracts 的 Python DTO 与 JSON Schema 同时演进，Backend 按 Worker 公布能力派发。旧 Worker 不接收新选择器，不丢字段后执行；不含时间轴的旧请求可继续发 v1。混版 Runtime 池按发布身份匹配，不能随机下发给旧副本。

新增 Runtime Kit 在 G2 前仅用于内部受控样例，不能出现在面向普通模型的可执行推荐结果；仅在文档中声明接口不构成能力开放。旧页面和旧构建继续按原策略运行。

## 错误和诊断

候选错误：`TIMELINE_SCHEMA_INVALID`、`TIMELINE_TARGET_INVALID`、`TIMELINE_DEPENDENCY_CYCLE`、`TIMELINE_PROPERTY_CONFLICT`、`TIMELINE_MEDIA_BLOCKED`、`TIMELINE_BUFFER_TIMEOUT`、`MODEL_ANIMATION_REFERENCE_STALE`、`TIMELINE_SNAPSHOT_UNAVAILABLE`、`TIMELINE_UNSUPPORTED`。WP02 冻结命名并映射现有检查 envelope；不另造顶层检查返回格式。

模型侧返回有界的定位和修复建议，详细内部轨道状态留在诊断记录。不得返回票据、存储键、原始媒体字节或完整 DOM/Three.js 场景树。

## HTTP 联调草案

以下为待实现的路径与字段，WP09/WP11 联动 OpenAPI、权限目录和客户端后才能调用。HTTP 使用 snake_case，Runtime 选择器使用上文 camelCase，转换只维护一处。

| 用途 | 路径与语义 |
| :--- | :--- |
| 默认最新截图 | 保留 `GET /api/v1/pages/{page_id}/screenshot`，仅使用默认 poster；不接受临时选择器改变其含义 |
| 外部异步截图 | 新增 `POST /api/v1/pages/{page_id}/screenshot-jobs`，支持 Idempotency-Key，返回 202 和 job |
| 外部任务读取 | 新增 `GET /api/v1/pages/{page_id}/screenshot-jobs/{job_id}`，返回 200 的状态、错误与成功结果摘要 |
| 外部临时图读取 | 新增 `GET/HEAD /api/v1/pages/{page_id}/screenshot-jobs/{job_id}/content`，成功后按现有私有截图响应规则返回图片 |
| Editor 任务 | 扩展现有 `POST /api/pages/{page_id}/screenshot-jobs` 与 `GET /api/pages/screenshot-jobs/{job_id}`；为临时结果增加受保护 content 入口 |
| 放映设置 | 扩展既有项目/路由的 slideshow/advance DTO，新增 timeline_end 和 timeline_timeout_ms，不新增旁路配置写入口 |
| 动作发现 | 扩展既有资产详情/analysis 与 workspace capabilities，不再建立第二个动作资产目录 |
| Worker 执行 | 新增 `POST /internal/render/v2/executions` 及 v2 的读取、取消、产物和消费确认路径；服务凭证与浏览器网络隔离沿用 v1 |

异步截图请求保留 viewport_width/height，可增加 target_page_version_no 和以下临时选择器：

```json
{
  "motion_snapshot": {
    "timeline_id": "product-intro",
    "at_label": "detail",
    "offset_ms": 600,
    "visual_mode": "full"
  }
}
```

有选择器即为临时请求，不能提升默认截图指针。成功 job 结果增加受保护的 content_url 与 applied_motion 摘要，后者含 timeline_id、sampled_time_ms、plan_digest、state_digest；保持有界，不返回执行票据。实际资源版本由任务快照捕获并按当前 attempt 围栏发布。

创建、轮询和读图均复核页面、任务与当前用户的工作空间归属；截图任务沿用页面可读与现有截图权限模型，不由渲染能力授予页面写权限。content 未就绪返回 409，鉴权与不可见目标沿用现有 401/403/404 语义。

请求结构不合法同步返回 422；能力/协议不支持、显式页版本冲突返回 409。标签不存在、动作过期等必须实际执行才能判断的问题，在已接受 job 的 failed/error_code 中返回，不能把事后错误伪装成最初 POST 的同步响应。默认更新指针继续走既有发布事务与版本复核。
