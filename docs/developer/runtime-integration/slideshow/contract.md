# 自动放映配置与接口契约

状态：M0 字段与行为已通过 [WP12 联调验收](./work-packages/wp12-m0-integration.md)；M1 的 `timer`、自动开始与单窗口自动放映已通过 WP21 开放；M2 的 `media_end`、`media_timeout_ms` 与演讲者自动放映已通过 [WP30 验收](./work-packages/wp30-m2-integration-release.md)并于 2026-10-18 开放（schema 2）。2026-10-21 WP08 将结构升为 schema 3，新增 `timeline_end` 与 `timeline_timeout_ms`；结构可解析但写入与能力声明仍由 G2 门禁关闭。2026-10-18 全屏放映统一模型调整了 `auto_start` 的运行语义，不改变字段、DTO 或存储；已发布事实以实际 DTO、OpenAPI 和契约测试为准，阶段定义见[总计划](./README.md)。

## 1. 配置归属与名称

Backend 拟新增独立 `schemas/slideshow.py`，定义严格 DTO 和统一解析器。数据库保存 API 规范化后的原始配置，导入、API、AI 业务工具均经过同一校验路径。

| 对象 | 拟定归属 | 对外字段 |
| :--- | :--- | :--- |
| 项目完整放映配置 | `Project.slideshow_config_json`，非空规范化 JSON | 项目创建、更新和详情的顶层 `slideshow` |
| 叶子路由动画覆盖 | `ProjectRoute.transition_json`，可空 JSON | 路由节点 `transition` |
| 叶子路由翻页覆盖 | `ProjectRoute.advance_json`，可空 JSON | 路由节点 `advance` |
| 叶子路由生效值 | Backend 派生，不另行持久化 | 路由响应只读 `effective_slideshow`，含 `transition` 与 `advance` |
| 当前播放状态 | 每个 Runtime Router 会话 | 不进入项目/路由 HTTP 写入模型 |

不把放映配置并入项目和工作空间样式共用的 `PresentationConfig`；项目应用样式或另存为样式均不携带放映设置。页面源码和 `Page` 资源不保存路由放映参数。

## 2. 首期字段

以下为 Backend 拟定的默认完整值，API 使用 snake_case，所有时间以整数毫秒表示：

```json
{
  "slideshow": {
    "transition": { "effect": "fade", "duration_ms": 400 },
    "advance": { "mode": "manual", "delay_ms": 5000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000 },
    "loop": false,
    "auto_start": false
  }
}
```

| 字段 | 约束 | 语义 |
| :--- | :--- | :--- |
| `transition.effect` | `none`、`fade`、`push` | 进入目标页的整页效果；翻回时推入方向反转 |
| `transition.duration_ms` | `none` 必须为 0；其它为 100–2000 | 动画时长，和页面停留时间分开 |
| `advance.mode` | `manual`、`timer`、`media_end`、`timeline_end` | 手动、停留指定时间、等待当前页媒体结束或等待页内时间轴结束后自动翻页；`timeline_end` 在 G2 前不可写入 |
| `advance.delay_ms` | 1000–3600000 | 从当前页就绪且过渡结束后计时；`manual` 保留该值但不运行计时，`media_end` 在无参与媒体时按该值停留 |
| `advance.media_timeout_ms` | 1000–3600000；省略时规范化为 300000 | 媒体等待上限；到期进入错误暂停，可重试、下一页或停止 |
| `advance.timeline_timeout_ms` | 1000–3600000；省略时规范化为 300000 | 页内时间轴的实际播放时间预算；用户暂停、后台等待与缓冲不推进，超时进入错误态 |
| `loop` | 布尔值 | 自动到达末页并满足该页完成条件后，回到第一个可放映叶子页 |
| `auto_start` | 布尔值 | 进入全屏放映时的初始自动推进模式：`true` 按页面 `advance` 自动推进，`false` 先进入手动；运行中可切换，不写回配置。正常预览、只读预览、捕获和导出上下文不启动放映 |

布尔值不得作为整数接受；字符串数字、浮点数、未知字段和显式 null 子字段都拒绝。缺省值由 Backend 在创建和旧数据升级时补齐；项目写入中显式给出的 `slideshow` 必须是完整对象，不由客户端猜补。

## 3. 覆盖与写入语义

- 项目创建省略 `slideshow` 时采用默认完整值；项目 PATCH 省略时保留，提供完整对象时替换，顶层 null 拒绝。
- `transition`、`advance` 按整组覆盖，提供对象时必须完整；组内不做部分字段继承。
- 新叶子路由省略或提供 null 表示继承项目对应组；已有叶子路由显式 null 清除该组覆盖。
- 为兼容旧客户端整树 PUT，已有节点省略新字段时，按旧树中的“完整路由路径＋页面绑定”保留覆盖；新节点省略时继承。实现需在删旧树前读取覆盖，不能依赖重建后会变化的路由 ID。
- 路由重命名、移动或重新绑定页面时，支持新契约的客户端显式携带完整覆盖值或 null；无法匹配的旧客户端操作按新节点继承处理。
- 分组节点不接受非 null 的 `transition` 或 `advance`，不提供章节级继承。
- 响应返回原始覆盖值及只读生效值；写请求不接受 `effective_slideshow`。修改项目默认值只影响继承项，不改显式覆盖。
- 自动翻页只使用现有可见叶子页目录与排序；手动边界导航保持原有行为，不因 `loop=true` 自动绕回。

示例为一次完整叶子节点写入：

```json
{
  "route_type": "page",
  "route": "overview",
  "order": 1,
  "hidden": false,
  "page_id": 123,
  "transition": { "effect": "push", "duration_ms": 600 },
  "advance": { "mode": "timer", "delay_ms": 8000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000 },
  "children": []
}
```

## 4. HTTP 接入与权限

在现有路径扩展字段，不新增旁路 YAML 写入口：

| 用途 | Editor/内部 API | External API v1 |
| :--- | :--- | :--- |
| 创建、读取项目 | `POST /api/projects`、`GET /api/projects/{id}` | `POST /api/v1/projects`、`GET /api/v1/projects/{id}` |
| 更新项目默认值 | `PATCH /api/projects/{id}` 顶层 `slideshow` | `PATCH /api/v1/projects/{id}` 顶层 `slideshow` |
| 外部结构化配置兼容入口 | 不新增 | `GET/PUT /api/v1/projects/{id}/configuration` 增加顶层 `slideshow`，PUT 省略时保留 |
| 读取、覆盖路由树 | `GET/PUT /api/projects/{id}/routes` | `GET/PUT /api/v1/projects/{id}/route-tree` |

创建请求和 External 创建 DTO 均需透传项目 `slideshow`；External configuration PUT 的 `slideshow` 不塞入现有 `configuration.presentation` 字典，读取时也与 `presentation` 并列。

权限沿用项目所属工作空间访问控制；External 沿用现有 operation、`project:read` / `project:write` 和写操作幂等契约。只更新放映设置不会创建页面变更重任务。

| 情形 | 拟定结果 |
| :--- | :--- |
| 字段类型、范围、枚举、分组配置或完整性错误 | 422，沿用现有请求校验错误格式并定位字段 |
| 项目、页面绑定无权访问或不存在 | 沿用现有对应资源错误与隐藏存在性规则 |
| 幂等键被不同放映参数复用 | 沿用现有幂等冲突；指纹必须包括新增字段和显式 null |
| 旧服务未声明 `media_end` 或 schema 2 | 422 或客户端能力预检失败；不得保存后静默执行为定时翻页 |

在现有 `GET /api/v1/capabilities` 响应增加可选的严格类型字段 `slideshow`；缺失/null 表示服务端没有声明本功能。M2 开放后的字段基线如下，已有 version/workspace/scopes/operations 字段继续保留：

```json
{
  "slideshow": {
    "schema_version": 3,
    "transition_effects": ["none", "fade", "push"],
    "advance_modes": ["manual", "timer", "media_end"],
    "single_window_auto_play": true,
    "presenter_auto_play": true,
    "capture_auto_play": false,
    "transition_duration_ms": { "min": 100, "max": 2000, "none": 0 },
    "delay_ms": { "min": 1000, "max": 3600000 },
    "media_timeout_ms": { "min": 1000, "max": 3600000 },
    "timeline_timeout_ms": { "min": 1000, "max": 3600000 }
  }
}
```

M0 只声明已贯通的动画和 `manual`；M1 出口声明 timer 与单窗口自动放映（2026-10-17）。M2 结构在 WP22 升为 schema 2 并追加 `media_timeout_ms` 范围；WP24 的真实媒体证据、WP26/WP30 的双窗口与捕获验收完成后，WP30 于 2026-10-18 开放 `media_end` 和 `presenter_auto_play=true`，捕获仍保持 `capture_auto_play=false`。WP08 将结构升为 schema 3 并追加 `timeline_timeout_ms` 范围；`timeline_end` 只有在 G2 真实编排验收通过后才进入 `advance_modes` 与写入白名单，结构升级本身不构成能力开放。能力必须对应实际发布的 Backend/Runtime 组合，不能仅因数据库已接受字段就声明可执行。Editor 通过同一 builder 派生的只读 `GET /api/system/slideshow-capabilities` 获取相同结构，仅在 `advance_modes` 声明后展示对应模式，避免内外两套能力判断。现有 `/standards/page`、`/standards/component` 仍维护源码规范，不把项目放映 Schema 复制到其中。

## 5. Runtime 下发契约

Backend 在路由产物根节点输出项目默认值，每个叶子页输出经 Backend 解析的完整生效组；Runtime 使用 camelCase。保留现有 `transitionDefaults` 和 `meta.transition` 接口形状。

```yaml
transitionDefaults:
  effect: fade
  durationMs: 400
playback:
  autoStart: false
  loop: true
  advanceDefaults:
    mode: timer
    delayMs: 5000
    mediaTimeoutMs: 300000
    timelineTimeoutMs: 300000
routes:
  - route: overview
    component: '@/views/page-code.vue'
    meta:
      title: 概览
      order: 1
      transition:
        effect: push
        durationMs: 600
      advance:
        mode: timer
        delayMs: 8000
        mediaTimeoutMs: 300000
        timelineTimeoutMs: 300000
```

API 原始覆盖、只读生效值和 Runtime 输出由同一 Backend 解析器产生；共享正反例约束 snake_case/camelCase 转换。Runtime 缺少新字段时使用旧行为兼容兜底，平台正常链路不得依赖该兜底作为配置来源。

预览 artifact 和构建 snapshot 固化配置及完整有序路由，现有窗口不热读新的业务配置。配置进入 artifact/build 的身份摘要；截图缓存是否失效按实际静态渲染输入判断，不能把每次停留时间变化都当作重新截图要求。

## 6. M2 扩展与会话规则

M2 在 `advance` 中增加 `mode=media_end` 和 `media_timeout_ms`（可省略，默认 300000，范围 1000–3600000）；三种模式均保留完整结构，新版数据升级/读兼容由 Backend 补齐。WP08 增加 `mode=timeline_end` 与 `timeline_timeout_ms`（默认 300000，范围 1000–3600000），Runtime 对应字段为 `timelineTimeoutMs`；`timeline_end` 写入在 G2 前明确返回校验错误，不静默降级为 timer。M2 的 `media_end` 扩展已在执行器、能力自省、Editor、CLI/MCP 与真实媒体/双窗口验收同时就绪后开放（2026-10-18）；WP08 的字段与代码合入不改变该开放状态。

- `media_end` 主动播放当前页非循环原生音视频，全部结束后翻页；循环背景媒体不参与等待。
- 没有参与媒体时按 `delay_ms` 停留；播放被策略阻止进入受阻态，播放失败或超时进入错误暂停态，提供重试、手动下一页或停止。
- 手动跳页清除旧计时和旧媒体回调；运行中从新页重新计算，暂停中保持暂停；停止保留当前页，重新开始从当前页重新计时。
- 暂停保留剩余时间，并只恢复本会话暂停前正在播放的媒体。手动页保持放映会话开启，等待用户下一页。
- 双窗口只有一个调度者；跨窗口只传命令和可验证状态，不以两套定时器同时推进。协议详情见 [Runtime 计划](./runtime.md)。

## 7. 兼容与包格式

旧项目升级为默认完整配置，旧路由覆盖保持 null；迁移不改页面源码，不把 Runtime fixture 中的示例动画写入真实项目。

项目模板包拟升级 schema 3，保存项目 `slideshow` 和路由原始覆盖。新导入器同时接受 1、2、3：旧包补默认值，新包严格校验；不能把当前 `{1, CURRENT}` 的校验直接替换成 `{1, 3}` 导致 v2 失效。复制页面资源不复制路由设置，整项目模板导入保留它们。

能力与版本组合、旧客户端往返和发布次序见[验收计划](./acceptance.md)。
