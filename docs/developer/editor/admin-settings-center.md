<!-- 文件功能：说明 Editor 系统设置管理中心的视图结构、路由配置和交互行为。 -->
# 系统设置管理中心

Editor 的「系统设置」视图为平台管理员提供在线配置管理界面，对应 Backend 配置解析层的类 B 配置项。

## 路由与鉴权

- **路径**：`/settings/platform/settings`
- **鉴权**：`require_platform_admin`，非管理员用户不可见该导航项。
- **所属布局**：`SettingsLayout.vue`，与用户管理、AI 管理共用「平台管理」侧栏分组。

## 视图结构

`AdminSettingsView.vue` 包含 5 个 Tab 页：

| Tab | 配置范围 | 关键交互 |
| :--- | :--- | :--- |
| 存储 | 资源存储驱动（本地 / S3）、S3 连接参数 | 测试连通性按钮（调用 `POST /api/v1/admin/settings/storage/test-connection`） |
| 常规 | 应用时区、站点标题 | 下拉选择 + 文本输入 |
| 安全 | 会话策略 | 开关 + 数值输入 |
| AI 运营 | 全局 AI 开关、Models.dev 同步、超时参数 | 手动同步按钮 + 模型目录状态展示 |
| 诊断 | 运行时日志级别、HTTP trace 开关 | 即时生效开关 |

## Safe-Mode 告警

当 Backend 检测到数据库中存在无法解析的配置值时：

- 降级到代码默认值（不 Crash-Loop）。
- 在 `GET /api/v1/admin/settings` 响应中返回 Safe-Mode 标记。
- 视图顶部展示告警横幅，提示管理员检查并修正问题配置。

## ENV 覆盖锁定

被环境变量覆盖的配置项：

- 在响应中标记 `source: "env"`。
- 视图中对应输入框显示锁定图标。
- Tooltip 提示「此配置已被环境变量覆盖，修改需在部署配置中操作」。
- 输入框置为只读。

## 参考

- [配置解析层](../backend/config-resolution.md)：三层优先级、防变砖和热替换的完整实现说明。
- [设置与管理用户指南](../../user/management/settings-and-admin.md)：面向平台管理员的操作说明。
