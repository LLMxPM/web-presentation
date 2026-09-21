# 时间存储与展示

## 数据库与接口

所有 ORM 时间列统一使用 `app.db.types.UTCDateTime`。写入时先转换为 UTC；PostgreSQL 保留 `timestamp with time zone`，SQLite 保留现有 `DATETIME` 格式并写入无偏移的 UTC 数值。数据库读回的 Python 值统一带 UTC 时区。

历史无时区时间直接视为 UTC，在读取时补齐时区，不推断原服务器时区，也不调整原有年月日时分秒。该规则同时覆盖 SQLite 历史数据和调用方传入的无时区时间。物理列类型没有变化，无需迁移或重写历史表；已有数据库默认时间与索引继续生效。

`created_at` 默认使用数据库当前时间，`updated_at` 在 SQLAlchemy 更新时取数据库当前时间。业务代码显式取时使用 `utc_now()`，包括构建任务、心跳、过期时间和租约。原生 SQL 更新仍需自行维护 `updated_at`。

接口中的日期时间使用带时区的 ISO 8601 字符串，UTC 后缀可以是 `Z` 或 `+00:00`。例如 `2026-09-21T02:00:00Z` 在上海业务时区显示为 `2026/9/21 10:00`。AI 运行态快照与 SSE 也遵循该规则。

## Editor 业务时区

`APP_TIMEZONE` 是业务时区的部署配置，默认 `Asia/Shanghai`。它控制新版本标签、业务编码日期以及 Editor 展示，不改变数据库 UTC 存储语义。

Editor 挂载前请求 `GET /api/system/settings`：

```json
{"app_timezone": "Asia/Shanghai"}
```

该 BFF 接口无需登录、没有请求参数，只返回公开业务时区，不返回数据库连接或凭证。成功响应为 HTTP 200；业务时区名称在 Backend 配置加载时校验。该路径不属于 External API v1。

Editor 使用返回的时区覆盖构建配置。配置请求失败时保留 `VITE_APP_TIMEZONE`，未设置时使用 `Asia/Shanghai`，允许应用继续启动。修改后端 `APP_TIMEZONE` 并重启 Backend 后，刷新 Editor 即可生效，无需重建前端。

前端时间字符串统一通过 `parseApiDate()` 解析；历史无时区的 ISO 日期时间直接补 `Z`。带 `Z` 或明确偏移的值保留原时间点。列表、令牌、供应商、AI 消息和会话列表按业务时区格式化；排序、取消等待计时也使用同一解析入口。

## 回归验证

- `backend/tests/unit/test_utc_datetime.py`：SQLite 写入和读取、旧数据补时区、UTC 条件查询、数据库默认值、PostgreSQL 列类型与全部模型时间列防漂移。
- `backend/tests/api/test_time_serialization.py`：旧时间经真实工作空间接口返回 UTC，以及公开业务时区配置。
- `editor/src/utils/timezone.test.ts`：无时区和多种偏移输入、毫秒精度、跨日展示、运行时业务时区覆盖。
- `editor/src/utils/setup-timezone.test.ts`：启动时同步配置与请求失败回退。
