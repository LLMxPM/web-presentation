# 开发术语表

| 术语 | 说明 |
| :--- | :--- |
| 控制面 | Backend 承载的数据、权限、任务和 AI 管理职责 |
| 数据面 | Runtime 执行预览与构建、Renderer 执行真实浏览器截图与页面诊断的职责 |
| preview artifact | Backend 为 Runtime 预览准备的短期上下文 |
| build snapshot | 一次构建固化的项目输入 |
| Runtime Kit manifest | Runtime 对页面和组件公开能力的清单 |
| HITL | Human-in-the-loop，AI 工具调用中的用户确认机制 |
| 契约测试 | 约束跨模块接口、manifest 和产物结构的测试 |
| 远程渲染服务 | 承载 Playwright Chromium 截图与渲染诊断的独立微服务（renderer/） |
