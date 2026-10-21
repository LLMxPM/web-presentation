# WP10 公共入口与预览控制

状态：待实施。主责：Runtime Kit / Editor。前置：[WP08](./wp08-host-slideshow-sync.md)、[WP09](./wp09-capture-export.md)。

## 输入与落点

以 WP02 定义的内部接口封装 usePageTimeline.v1 与 AssetAudio/AssetVideo/AssetModel.v2，复用内部执行器。Editor UI 实施前完整阅读根 DESIGN。

## 交付

- 发布一个模型常用入口：definition 与 bindings 分开、类型限制目标 key 和轨道，少量预设共享同一计划编译器。
- 更新 Runtime Kit manifest、usage、constraints、参数 Schema 与返回示例；v1 行为保留，不让旧源码获得隐式自动播放。
- 内部样例可独立预览组件轨道片段，但实际页面仍只有一个 transport；销毁预览作用域释放目标。
- Editor 增加显式播放、暂停、重播、定位、状态与偏好模拟；默认 poster，调试偏好只影响当前预览，不改变操作系统设置。
- 增加 timeline_end 项目/路由表单与继承说明、动作摘要展示和定位错误；不提供首期图形轨道编辑器。
- 模型写入与可视化样式编辑继续以源码为权威；预览控制不写回另一套时间轴数据。

## 验证与通过条件

覆盖 A03、A12、A15 和 B01–B05 的使用体验。类型错误在准确的字段出现，运行错误映射到具体轨道；不能要求模型手写事件监听、缓冲处理或 RAF。

Editor 组件/布局验证、Runtime Kit manifest 跨端校验、旧 v1 页面回归，以及生产裁剪后的入口加载均通过。

## 交接

向 WP11 提供可执行示例、真实 import path、能力隐藏规则与标准错误示例；G2 前保持普通用户的能力关闭。

## 实施记录

- 代码版本、manifest 与公开入口：待回填。
- 实际命令、结果、预览截图和旧页面证据：待回填。
- 未覆盖项：待回填。
