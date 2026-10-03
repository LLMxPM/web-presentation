<!-- 文件功能：说明 Backend 配置解析层的三层优先级、类 B 规格注册表、防变砖机制和热替换约束。 -->
# 配置解析层

`web-presentation` Backend 使用三层优先级配置解析，支持 Web UI 热更新运行配置而不需要重启容器。

## 三层优先级

```text
ENV 覆盖  ≻  DB（system_settings 表）  ≻  代码常量
```

- **ENV 覆盖**：环境变量始终具有最高优先级。用于部署必填项（类 A）和紧急救砖。
- **DB 配置**：`system_settings` 表存储通过 Web UI 修改的运行配置（类 B）。修改即热生效。
- **代码常量**：`AppSettings` 中的默认值，不需要任何配置即可正常启动。

## 配置分类

| 分类 | 数量 | 说明 | 修改方式 |
| :--- | :--- | :--- | :--- |
| **类 A** | ~9 项 | 必须留在 ENV 的部署必填项（如 `DATABASE_URL`、`AI_SECRET_ENCRYPTION_KEY`） | 修改 `.env` + 重启容器 |
| **类 B** | 19 项 | 可在 Web UI 维护的运行配置（如存储驱动、时区、AI 开关） | Web UI 热更新 |
| **类 C** | 其余 | 调优常量（如租约超时、轮询间隔），保持代码默认值 | 修改 ENV（高级运维） |

类 B 规格注册在 `SYSTEM_SETTING_SPECS`（19 项），每项声明 key、类型、默认值、校验规则和变更影响。

## 防变砖三层

1. **前置校验**：保存前对输入值进行 dry-run 验证，非法值拒绝写入。
2. **Safe-Mode 降级**：数据库中的非法配置不导致 Crash-Loop。启动或热加载时若 DB 值无法解析，自动降级到代码默认值，并在日志和 Web UI 展示 Safe-Mode 告警。
3. **ENV 紧急否决权**：任何类 B 配置都可被同名环境变量覆盖，确保改坏数据库后仍可通过 ENV 救砖。

## 热替换机制

- `config.py` 使用并发安全单例，支持显式失效和热替换。
- `PUT /api/v1/admin/settings` 写入 DB 后立即失效缓存单例，下一次读取重新解析三层。
- 确实无法热替换的配置项（如 `CORS_ORIGINS`，在 FastAPI 启动期绑定中间件）归类 A，不硬凑热更新。

## 多副本约束

- `ASSET_STORAGE_DRIVER=local` 在 `BACKEND_MULTI_INSTANCE=true` 下拦截（本地存储不支持多副本共享）。
- 多副本环境下 DB 配置变更对所有实例生效（共享同一数据库），ENV 覆盖需在所有实例上一致设置。

## API

| 端点 | 方法 | 鉴权 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/v1/admin/settings` | GET | `require_platform_admin` | 返回全部配置项当前值与来源 |
| `/api/v1/admin/settings` | PUT | `require_platform_admin` | 更新类 B 配置并热生效 |
| `/api/v1/admin/settings/storage/test-connection` | POST | `require_platform_admin` | 异步测试 S3 连通性 |
| `/api/system/settings` | GET | 公开 | 返回热生效时区等公开配置 |

## 参考

- [环境变量治理](../architecture/environment-variable-governance.md)
- [部署环境变量](../../deployment/production/env-vars.md)
- [Editor 系统设置管理中心](../editor/admin-settings-center.md)
