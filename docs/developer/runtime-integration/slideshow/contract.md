# 放映配置与接口契约

当前配置版本为 schema 4，运行态使用 Scene/Deck。工程进度见[工作包](../playback-redesign/work-packages/README.md)，真实浏览器与产物验收集中在 C3。

## 配置与继承

项目创建、详情和 PATCH 顶层 `slideshow` 使用严格 DTO：

```json
{"transition":{"effect":"fade","duration_ms":400},"advance":{"mode":"manual","delay_ms":5000,"completion_delay_ms":300},"loop":false}
```

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `transition.effect` | `none/fade/push` | 进入目标页的整页效果 |
| `transition.duration_ms` | none 为 0，其余 100–2000 整数 | 独立于页内 Scene |
| `advance.mode` | `manual/timer/scene_end` | 手动、定时、本页有限任务实际完成 |
| `advance.delay_ms` | 1000–3600000 整数 | 仅 timer 使用；过渡和资源就绪后计时，到点终止本页并翻页 |
| `advance.completion_delay_ms` | 0–3600000 整数，默认 300 | scene_end 的有限任务全部完成后停留；零表示完成后立即推进 |
| `loop` | 布尔值 | 自动推进末页后返回首页 |

scene_end 必须有 blocking 完成目标；无限 ambient 不计入完成。没有目标、任务失败或准备失败须显式报告，不能改成定时推进。任务 prepare/completion watchdog 属于 Scene 执行边界，不是项目中的可配置超时。

项目省略 slideshow 采用默认值；PATCH 省略保留，提供完整对象整体替换，顶层 null 拒绝。叶子路由 `transition/advance` 按组覆盖，null 恢复继承；组内不逐字段继承。整树 PUT 的既有节点省略字段，按完整路由路径和页面绑定保留原覆盖；新节点省略则继承。分组禁止非 null 覆盖。只读 `effective_slideshow` 由 Backend 计算。应用样式不修改放映配置。

所有整数拒绝布尔、字符串、浮点、显式 null 和越界值；未知字段拒绝。删除的 auto_start、media_end、timeline_end、media_timeout_ms、timeline_timeout_ms 不做映射。播放由显式 start 开始，hold/release 只影响自动推进，不暂停 Scene，也不改写配置。

## API 与版本

Editor 使用 `/api/projects`、`/api/projects/{id}`、`/api/projects/{id}/routes`；External 使用 `/api/v1/projects`、`/api/v1/projects/{id}`、`/api/v1/projects/{id}/configuration`、`/api/v1/projects/{id}/route-tree`。权限、工作空间隔离和写入幂等沿用既有操作。非法写入为 422，幂等键参数变化为 409。

`GET /api/system/slideshow-capabilities` 与 External 工作空间 capabilities 的 `slideshow` 声明 schema_version=4、三种推进模式、delay_ms 范围及 completion_delay_ms 的零下限。`slideshow.audio` 三项固定描述已实现的资源、旁白和 cue 能力，不再作为阶段门禁。`GET /api/system/scene-capabilities` 及 External `scene` 声明 blocking/ambient、visual/model3d/media/custom 与独立静态呈现；旧 timeline-capabilities 和 timeline 字段已删除。

Backend 读取旧项目/路由配置返回 409 `SLIDESHOW_CONFIG_UNSUPPORTED`，要求按 schema 4 重新保存。数据库迁移只改变新行默认值，不转换既有 JSON。模板包版本为 schema 5，旧 1–4 包明确拒绝，须重新导出；当前包仍验证 cue 资源、逐路由覆盖与完整设置。

Runtime 下发结构：

```json
{"transitionDefaults":{"effect":"fade","durationMs":400},"playback":{"schemaVersion":4,"loop":false,"advanceDefaults":{"mode":"manual","delayMs":5000,"completionDelayMs":300}},"routes":[]}
```

预加载与外部 routes 配置在进入路由前严格校验，覆盖隐藏页和分组内叶子；旧 schema、旧字段和旧模式抛出 `RUNTIME_SLIDESHOW_SCHEMA_UNSUPPORTED`，清除旧成功缓存。构建与诊断在执行 Worker 前返回同码 409；旧 artifact/构建快照需要重新生成。静态组件 fixture 可以没有 playback，不能携带旧 playback 蒙混通过。

## 验证边界

共享 fixture 位于 `tests/fixtures/slideshow-contract-cases.json`；覆盖继承、序列化、零停留、严格类型、旧字段拒绝。迁移测试实际执行 SQLite 默认变更并检查 PostgreSQL 离线 DDL；不代表真实 PostgreSQL 或开发数据库已升级。Editor 复用生成 DTO 和共享字段组件。CLI 跨仓适配；MCP 快照失配按 B5 记录为非阻塞。
