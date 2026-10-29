# 远程渲染服务

Backend 负责渲染请求、调度、租约、结果保存和业务提交；独立 Renderer 执行截图与页面诊断中的 Chromium 工作。Backend 进程不启动 Playwright 或 Chromium。历史改造方案与交付记录见[远程渲染设计归档](../../archive/developer-work-2026-10/remote-render-service-design.md)。

## 当前边界

- 页面截图与诊断统一形成持久化 `render_requests` 和执行 attempt。Backend 按租约、期限与配额派发；过期、取消及迟到结果不能越过当前 attempt 的提交围栏。
- Renderer 不连接业务数据库。每个 attempt 使用独立 Chromium 与 Context，执行后释放浏览器进程、临时产物和槽位；控制 API 使用服务身份凭证，凭证缺失时拒绝执行。
- Renderer 浏览器使用本次预览 artifact 的票据 P 访问隔离预览源站；Runtime 或构建 Worker 回源使用内部服务票据 S。具体入口见[预览源站接入](../runtime-integration/preview/README.md)。
- 页面诊断先完成，附图再捕获；图片失败不能覆盖已完成的诊断。组件远程渲染诊断协议保留在 Renderer 和契约包中，内容助手当前不调用该业务入口。

## 修改与验证入口

| 范围 | 事实源或入口 |
| :--- | :--- |
| 请求、回执、结果 Schema 与错误码 | [`packages/render-contracts`](../../../packages/render-contracts/) |
| Renderer 服务与生命周期 | [Renderer 开发说明](../../../renderer/README.md) |
| Backend 调度和页面截图 | [`backend/app/services/rendering`](../../../backend/app/services/rendering/)、[预览 artifact 与构建任务](./preview-artifacts.md) |
| 租约与任务状态词汇 | [统一任务运行时契约](../architecture/task-runtime-contract.md) |
| 发布环境待验证事项 | [发布检查清单](../../deployment/release-checklist.md) |

修改执行、取消、期限或产物协议时，联动契约包、Renderer 和 Backend 协调器测试；测试选择按 `dev-start-test` 技能执行。
