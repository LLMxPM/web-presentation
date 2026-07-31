# 接口契约索引

本文档索引需要跨模块同步维护的接口契约。具体 API 细节以 Backend schema、Runtime 文档和契约测试为准。

## Editor 与 Backend

- 登录、会话和用户信息。
- 工作空间、项目、页面 CRUD。
- 资源、组件、主题、样式和字体注册。
- AI 会话、工具披露、工具确认和账户 AI 设置。
- 构建任务、截图和预览状态。

### 字体族与字体文件

字体按字体族（Family）管理，字体文件（Face）挂在字体族下：

- 字体族端点：`GET /workspaces/{id}/font-families`（分页，每项内嵌全部 face）、`PATCH /workspaces/{id}/font-families/{family_id}`（重命名，同工作空间内唯一）、`DELETE /workspaces/{id}/font-families/{family_id}`（仅限无 face 且未被主题绑定，否则 409）。
- Face 端点沿用 `/workspaces/{id}/fonts`：创建/更新请求使用 `family_name` 字符串（service 内 get-or-create 字体族），响应保留 `font_family`（由 family.name 派生）并新增 `family_id`。删除 face 后若字体族变空且未被主题绑定，级联删除空族。
- `font_weight` 允许单值（如 `400`）或可变字体范围（如 `100 900`，min<=max）；`font_style`、`font_display` 为受限枚举，写入前统一校验。
- 主题创建/更新的三个字体字段语义为 `*_font_family_id`（绑定字体族）；主题 `typography` 输出字体族名，字体 Bundle 按族下发全部启用 face，Runtime 逐 face 生成 @font-face 由浏览器按字重/样式自动匹配。

## Runtime 与 Backend

- 预览上下文读取。
- 资源和配置包读取。
- build snapshot 拉取。
- 构建产物上传。
- JWKS、预览令牌、构建令牌和诊断令牌校验。

## AI 工具体系

- `/ai/agent-catalog`
- `/ai/agent-configs`
- 工具说明、参数 JSON Schema、调用示例和返回示例。

## 测试入口

跨模块契约变化时，优先补充或更新 `tests/contracts/`，再根据影响范围补 Backend、Editor、Runtime 或 E2E 测试。
