# 放映配置与运行时接入

本页是开发者定位放映实现的入口。用户操作见[放映指南](../../../user/workflows/slideshow.md)；字段、默认值、继承与错误语义以[放映契约](./contract.md)和实际 DTO 为准。

## 当前行为

- Backend 保存项目默认放映设置与路由逐页覆盖，并向预览和构建提供只读快照。
- Runtime 在根元素全屏后开始放映；普通预览不推进。定时、媒体结束、手动翻页及演讲者双窗口按同一会话状态执行。
- Renderer、截图、PDF、PPTX 和打印使用静态执行上下文，不启动自动推进或媒体播放。
- 产品级远端无人值守放映尚需独立交付；本地构建产物的历史长稳证据不代表该能力已开放。

## 修改入口

| 需求 | 代码或文档入口 |
| :--- | :--- |
| 字段与服务端默认值 | [`schemas/slideshow.py`](../../../../backend/app/schemas/slideshow.py)、[`core/slideshow_defaults.py`](../../../../backend/app/core/slideshow_defaults.py)、[放映契约](./contract.md) |
| Editor 项目和逐页设置 | [`ProjectPresentationConfigDialog.vue`](../../../../editor/src/components/project/ProjectPresentationConfigDialog.vue)、[`project-route-slideshow.ts`](../../../../editor/src/utils/project-route-slideshow.ts) |
| Runtime 放映状态与控制 | [`usePlaybackHost.ts`](../../../../runtime/src/runtime-shell/playback/usePlaybackHost.ts)、[`PlaybackHostBridge.vue`](../../../../runtime/src/runtime-shell/playback/PlaybackHostBridge.vue) |
| 版本化页面能力 | [Runtime Kit 能力说明](../../runtime/runtime-kit-capabilities.md) |
| 测试选择与环境 | [`dev-start-test`](../../../../.agents/skills/dev-start-test/SKILL.md) |

修改字段或运行语义时，同步检查 Backend DTO、Editor 映射、Runtime 消费、预览/构建快照和跨模块契约。旧的分阶段计划与 33 个工作包保留在[放映实施归档](../../../archive/developer-work-2026-10/slideshow/README.md)中，用于追溯验收证据。
