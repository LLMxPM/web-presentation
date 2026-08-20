# 未提交更改修复报告

## 修复结果

已按最小改动原则完成以下功能性修复：

1. 组件 Mutation 使用统一源码指纹，修复 `component_edit` 读取不存在字段导致的必失败问题。
2. Mutation Finalizer 对页面和组件增加目标行锁及版本/草稿指纹复核，避免慢诊断期间覆盖并发修改。
3. External API 禁止通过项目更新修改所属工作空间，防止 PAT 跨授权空间迁移项目。
4. 构建任务创建前锁定项目行，避免并发请求创建多个活动构建任务。
5. 六类批量归档路由接入现有 `IdempotencyService`，重复 Key 重放原响应。
6. 组件结构化编辑允许版本基线 `0`，并支持/返回草稿指纹。
7. `validate.code` 的 Scope 注册改为页面或组件 Scope 任一满足，并同步 capabilities 与 guides 元数据。
8. PAT 创建请求拒绝重复 `workspace_ids`。
9. CLI 工作空间列表改用后端实际返回的 `code` 字段。
10. PAT 管理页复选框阻止点击冒泡，避免状态被切换两次。

## 未纳入本轮

上传后数据库事务失败时的孤立对象回收需要额外的存储清理策略；按本轮“避免过度设计”的范围暂不引入 staging/outbox 机制。

## 验证

- Backend Ruff：通过。
- External、PAT、幂等、Mutation 测试：16 个通过；有 6 个 aiosqlite 事件循环关闭警告。
- 组件 Mutation、项目构建相关测试：24 个通过。
- CLI 测试：3 个通过。
- Editor 类型检查：通过。
- `git diff --check`：通过。
- Alembic `check`：未执行成功，当前环境无法连接配置的 PostgreSQL（`WinError 1225`）。
