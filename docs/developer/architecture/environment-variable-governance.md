<!-- 文件功能：环境变量三分类、配置解析优先级、热更新边界、密钥治理与安全防线的永久架构契约；执行排期不在本文。 -->
# 环境变量治理与配置 Web UI 迁移

更新日期：2026-10-02
状态：架构契约（永久文档）
面向对象：平台架构师、后端与前端开发者、运维交付人员

> 本文只维护**长期成立的契约**：变量三分类、按部署形态的差异、配置解析优先级、热更新边界、密钥治理与安全防线。批次、排期、门禁改动与验收状态见[现行执行计划](../../temp/plans/deployment-form-and-config-governance-plan-2026-10-02.md)；本文不复制排期，避免两处漂移。

---

## 1. 背景与治理目标

### 1.1 现状与痛点

全仓对外暴露的环境变量接近百项（`deploy/.env.example` 96 项、`deploy/runtime.env.example` 19 项，`AppSettings` 共 155 个字段）。实际部署与运维中暴露出四个核心痛点：

1. **认知负荷过重**：部署模板暴露数十个微观参数（心跳、租约、调度轮询、Worker 内存回收比例、内部通信 Audience），新部署者无法区分「哪些必须改」「哪些千万不能改」。
2. **密钥生成与对齐门槛高**：部署前必须运行 Python 脚本生成 Fernet 密钥（`AI_SECRET_ENCRYPTION_KEY`），并手工创建 `render_service_credential` 凭证文件且设置 `0400` 权限，格式稍有不慎即触发 fail-closed 拒绝启动。
3. **运维与业务管理严重耦合**：切换对象存储、调整业务时区、开关 AI 目录同步等纯业务配置，必须改环境变量并重启整个 Docker 堆栈；缺乏表单校验与连通性即时测试，极易因输入错误导致服务崩溃。
4. **轻量版未能开箱即用**：`compose.sqlite-lite.yml` 面向单机与个人试用，编排文件内仍列出 50 余项环境变量并要求手工密钥文件；而 HEAD 模板还把 Renderer 拆成独立容器，与用户文档描述的「单容器内置浏览器」不同构。

### 1.2 治理目标

- **部署方式只有两种**：生产（PostgreSQL + Redis，多容器）与 Lite（SQLite + memory，**单镜像单容器**）。
- **极致精简环境变量**：生产必填从近百项压缩到约 9 项；**Lite 必填为 0 项**，一条 `docker compose up -d` 即可完整可用（含截图与构建，不是「能启动但渲染静默不可用」）。
- **业务与运营配置收归 Web UI**：存储、业务时区、会话策略、AI 运营参数、日志级别移入管理后台。
- **配置更新不重启**：类 B 配置全部进程内热更新；类 A 变更走「改 `.env` + 重启容器」的常规运维路径，**不提供 Web UI 触发的进程重启能力**（见 §3.3 决策依据）。
- **坚固的纵深防御**：在免除人工密钥配置的同时，依托网络隔离、网关路由白名单、高熵自生凭证与沙箱降权保证内部服务安全。

---

## 2. 环境变量三分类治理矩阵

```mermaid
pie title 环境变量治理分类占比
    "类 A: 必须保留在 ENV (底座基础设施)" : 9
    "类 B: 移至 Web UI (存储/时区/运营)" : 15
    "类 C: 内置/代码常量/自动推导" : 60
```

### 2.1 【类 A】必须保留在环境变量中（约 9 项）

此类是服务启动的物理前提（没有数据库连接串就无法读取任何持久化配置），或在应用启动阶段一次性绑定：

| 变量名称 | 默认值/示例 | 必须留在 ENV 的原因 |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://...` 或 `sqlite+aiosqlite://...` | 读取任何持久化配置与运行态模型的前提；同时是部署形态判定输入（`db/profile.py`）。 |
| `REDIS_URL` | `redis://...` 或 `memory://lite` | 分布式运行态连接串；Lite 固定 `memory://lite`。 |
| `BACKEND_PUBLIC_BASE_URL` | `https://presentation.example.com` | 浏览器访问平台的公网根地址。 |
| `RUNTIME_PUBLIC_BASE_URL` | `https://presentation.example.com/runtime` | 浏览器访问演示预览的公网基址；同域模式可自动拼接 `/runtime`。 |
| `CORS_ORIGINS` | `["https://presentation.example.com"]` | FastAPI CORS 中间件在应用启动阶段绑定（`app/main.py:241-242`），无法热替换。 |
| `SESSION_SECURE` | `true` / `false` | Cookie Secure 标记，取决于接入层是否为 HTTPS。 |
| `AI_SECRET_ENCRYPTION_KEY` | Fernet 密钥 | **加密数据库内的模型供应商凭证**，多 Backend 必须实例间同一把（`signing_identity.py:275-284` fail-closed），且是备份恢复与密钥轮换的锚点。生产必填并进备份；Lite 首启自动生成（见 §4.2）。 |
| `DEFAULT_ADMIN_PASSWORD` | 强随机口令 | 仅首次启动无用户时播种管理员初始口令。生产必填；Lite 首启自动生成并一次性告知。 |
| `BACKEND_MULTI_INSTANCE` | `false` | 多副本集群显式声明，触发启动期共享密钥、对象存储与运行态的严格校验。 |

> `RUNTIME_RSA_PRIVATE_KEY` / `RUNTIME_RSA_PRIVATE_KEY_FILE`、`RUNTIME_BUILD_WORKER_CREDENTIAL`、`RENDER_SERVICE_CREDENTIAL(_FILE)` 属**条件类 A**：多副本生产必须显式提供且实例间一致，Lite 单实例可自动生成或省略（见 §4.2）。

### 2.2 【类 B】应当移到 Web UI 管理后台的配置（约 15 项）

改为在系统管理后台维护（仅 `platform_admin` 可见，鉴权复用 `api/dependencies.py:32` 的 `require_platform_admin`），保存在数据库 `system_settings` 表：

| 模块 | 涉及变量 | Web UI 位置 | 核心收益 |
| :--- | :--- | :--- | :--- |
| **存储配置** | `ASSET_STORAGE_DRIVER`<br>`S3_ENDPOINT_URL`<br>`S3_ACCESS_KEY`<br>`S3_SECRET_KEY`<br>`S3_BUCKET`<br>`S3_PUBLIC_BUCKET`<br>`S3_REGION`<br>`S3_PUBLIC_BASE_URL` | 系统设置 → 存储管理 | 默认本地存储启动，部署阶段无需理会 S3；界面提供「测试连接」即时验证 AK/SK/Bucket 权限，杜绝重启崩溃；支持动态切换驱动与查看容量。 |
| **常规设置** | `APP_NAME`<br>`APP_TIMEZONE` | 系统设置 → 常规 | 平台品牌名自定义；业务时区下拉选择，前端即时响应。 |
| **安全策略** | `SESSION_TTL_HOURS`<br>`PAT_MAX_ACTIVE_TOKENS`<br>`PAT_MAX_TTL_DAYS` | 系统设置 → 安全 | 动态控制会话有效时长与 PAT 发放上限。 |
| **AI 运营** | `AI_ENABLED`<br>`AI_MODEL_CATALOG_SYNC_ENABLED`<br>`AI_IMAGE_TRANSPORT_MODE`<br>`AI_AGENT_STREAM_IDLE_TIMEOUT_SECONDS` | 系统设置 → AI 运营 | 全局 AI 总开关、模型目录同步触发、图片传输与思考超时控制。 |
| **系统诊断** | `LOG_LEVEL`<br>`AI_LLM_HTTP_TRACE_ENABLED` | 系统设置 → 诊断监控 | 运行时热调日志级别，排查问题免停机。 |

类 B 的准入判据：**取值只在请求处理或任务发起时读取**，改值后下一次读取即生效，且不存在跨实例一致性前提。不满足判据的项必须留在类 A（见 §3.2）。

### 2.3 【类 C】基本不需要用户配置（内置/代码常量/自动推导，约 60 项）

全部从部署模板与 Compose 文件剔除，由系统内聚治理，但保留在 `AppSettings` 默认值中作为极端调优入口：

1. **内部通信 Audience 契约**：`RUNTIME_SERVICE_TOKEN_AUDIENCE`、`RUNTIME_PREVIEW_TOKEN_AUDIENCE`、`RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE`、`AI_AGENT_OS_ID` 收敛为代码常量。
2. **容器内网默认通信地址与挂载路径**：`RUNTIME_BASE_URL`、`RUNTIME_BACKEND_API_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL`、`RUNTIME_SERVER_BASE_PATH`（自动从 `RUNTIME_PUBLIC_BASE_URL` 提取路径）。
3. **微观调度与算法参数**：`DURABLE_JOB_LEASE_SECONDS`、`AI_PAGE_MUTATION_*`、`MUTATION_JOB_*`、`PROJECT_BUILD_*`、`RENDER_SCHEDULER_*` 等租约/心跳/轮询/重试参数；禁止污染常规部署模板，移除后须在 `docs/developer/deployment/env-vars.md` 保留「隐式调优参数」说明，不静默消失。
4. **机器间通信凭证**：`RUNTIME_BUILD_WORKER_CREDENTIAL`、`RENDER_SERVICE_CREDENTIAL` 在单容器形态下由入口脚本生成并对齐，免去人工创建（见 §4.2）。

> 注意分类边界：`AI_SECRET_ENCRYPTION_KEY` **不属于本类**。它不是内部通信密钥，而是数据静态加密密钥，丢失即导致库内模型凭证不可解密，因此归入类 A（§2.1）。

### 2.4 部署形态与分类的关系

| 形态 | 类 A 必填 | 密钥来源 | 模板 |
| :--- | :--- | :--- | :--- |
| **Lite 单容器** | 0 项（`DATABASE_URL`/`REDIS_URL`/回环地址由镜像与入口脚本预置） | 首启自动生成；`AI_SECRET_ENCRYPTION_KEY` 持久化到数据卷，机器间凭证每次启动生成不落盘 | `compose.sqlite-lite.yml` |
| **生产 · 单 Runtime 全角色** | 约 9 项 | 显式 `.env`；`AI_SECRET_ENCRYPTION_KEY` 与签名私钥进备份集 | `compose.prod.yml` |
| **生产 · 分角色** | 同上，另加 `runtime.env`（**不得含任何平台密钥**） | 同上；Runtime 三角色只读 `runtime.env`，避免平台密钥进入编译用户代码的容器（`compose.runtime-roles.yml:7`） | `compose.runtime-roles.yml` |

「生产」的两种规模共用同一套类 A 口径与同一个 `.env`；它们的差异只在编排拓扑，不产生第三套变量分类。`runtime.env` 的密钥边界由防漂移门禁守护。

---

## 3. 配置解析与重载契约

### 3.1 控制面与执行面的解耦

**Backend 是唯一的平台控制面**，Editor、Runtime、Renderer 是无状态或计算执行面：

```mermaid
flowchart TD
    subgraph Browser["浏览器端"]
        Editor["Editor (前端 SPA)"]
    end

    subgraph ControlPlane["控制面 (唯一持有配置)"]
        Backend["Backend (FastAPI)\nDB / 存储 / 权限 / AI / 时区"]
    end

    subgraph DataPlane["无状态计算执行面 (不持有业务配置)"]
        Runtime["Runtime (Vue/Vite)\n页面预览 / 构建编译"]
        Renderer["Renderer (Playwright)\n无头浏览器截图执行"]
    end

    Editor -- "读取 / 保存配置" --> Backend
    Backend -- "RS256 JWT 验签驱动" --> Runtime
    Backend -- "派发单次截图任务" --> Renderer
```

- **Editor**：纯静态 SPA，配置更新后重新读取或刷新页面即可，无进程重启概念；
- **Renderer**：无状态 Worker，只接收单次 HTTP 任务包，不感知业务配置；
- **Runtime**：通过 Backend JWKS 验签，资源回源走带签名 URL，不感知存储或业务变动；
- **结论**：类 B 配置的更新只需 Backend 处理，执行面零影响。

### 3.2 热更新机制要求

「热更新生效」不是一句承诺，必须满足以下三条实现约束：

1. **显式的缓存失效入口**：`get_settings()` 是 `@lru_cache`（`app/core/config.py:810`）。配置覆盖层写入数据库后，必须提供受控的缓存失效与重建路径，并保证并发请求下不读到半更新状态。
2. **消费点分类**：落地前先普查消费点，按「读时取值 / 启动期绑定」分类。已知读时取值：`asset_storage_drivers.py:212`、`object_storage_service.py:50`、`auth_cookie.py:15-18`、`auth_service.py:52,89`。已知启动期绑定：`main.py:241-242`（CORS 中间件）。**确实无法热替换的项必须归入类 A**，不得为了「全部热更新」的表述而保留伪热更新。
3. **启动期守卫重跑**：部分不变量只在启动期校验，热切换后必须重新校验。至少包括 `signing_identity.py:304-313` 的「多 Backend 必须使用共享对象存储（`ASSET_STORAGE_DRIVER=s3`）」——在 Web UI 把驱动从 s3 改回 local 时，多副本部署必须被拒绝而不是静默降级。

### 3.3 决策：不提供 Web UI 触发的进程重启

**结论：类 A 变更 = 改 `.env` + 重启容器，由编排层（Docker/K8s）负责；Backend 不实现 `POST /admin/system/restart` 之类的自杀重启接口。**

依据：

1. **没有触发场景**：需要重启才能生效的配置（CORS、Cookie Secure 等）全部属于类 A，而类 A 本就只能改 `.env`。Web UI 改不到类 A，「保存并重启」就没有入口。
2. **多副本下语义不成立**：生产可能运行多个 Backend 副本，重启收到请求的那一个实例既不解决 CORS 变更（其余副本仍是旧值），也无法保证整池一致；正确动作是改配置后由编排层滚动重启。
3. **避免新增高危能力**：一个可被管理员触发的进程自杀接口，会把「配置错误」升级为「服务不可用」，并与升级排空、租约回收和 Run 收敛语义纠缠。

代价与补偿：改类 A 需要容器重启，运维路径与今天一致；文档须写清「哪些变量改完必须重启、哪些即时生效」，避免用户误以为 Web UI 能改一切。

### 3.4 配置解析优先级

$$\text{生效配置} = \text{环境变量 (ENV 覆盖)} \succ \text{数据库 Web UI 配置} \succ \text{代码默认常量}$$

```mermaid
flowchart TD
    Read["读取某项配置 (如 S3_BUCKET)"] --> EnvCheck{"环境变量存在且非空？"}
    EnvCheck -- "是 (救砖 / 集群强制覆盖)" --> UseEnv["采用环境变量值 (最高优先级)"]
    EnvCheck -- "否" --> DBCheck{"数据库 system_settings 存在？"}
    DBCheck -- "是" --> UseDB["采用 Web UI 配置"]
    DBCheck -- "否" --> UseDefault["采用代码出厂默认值"]
```

ENV 最高优先级是**防变砖安全网**，不是可选特性：管理员在 Web UI 改坏配置导致无法登录时，运维只需在 `.env` 显式声明同名变量即可覆盖数据库值完成救砖。

### 3.5 防变砖三层防护

1. **前置 Dry-Run 与连通性实测**：Web UI 提交前做 Pydantic 校验与网络连通性实测（如 S3 发起一次握手），失败禁止保存。
2. **启动异常降级（Safe-Mode Fallback）**：数据库中非法值导致解析失败时，捕获异常并降级回退到代码默认安全值启动，记录告警并在 Web UI 顶部提示管理员修正，**绝不进入 Crash-Loop**。
3. **ENV 紧急否决权**：见 §3.4。

三层都必须有正例与负例证据，其中「非法 DB 值不得导致 Crash-Loop」必须实测，不能以代码审查代替。

---

## 4. 密钥治理与纵深防御

### 4.1 五道防线

```mermaid
flowchart LR
    Ext["外部公网流量"]

    subgraph Host["宿主机网络"]
        Port8080["唯一映射端口"]
    end

    subgraph InternalDocker["Docker 隔离网络 (外部不可达)"]
        Nginx["Nginx Gateway\n【第二道: 路由白名单】"]
        Backend["Backend\n【第四道: 高熵自生凭证】"]
        Runtime["Runtime\n【第五道: UID 降权沙箱】"]
        Renderer["Renderer\n【第三道: HMAC / RS256 校验】"]
    end

    Ext -. "尝试直连内部端口" .-> Block1["【第一道: 端口零暴露】"]
    Ext --> Port8080 --> Nginx
    Nginx -. "非白名单路径" .-> Block2["直接拦截"]
    Nginx -- "仅代理公开路由" --> Backend
```

1. **网络层隔离**：内部服务端口只在 Docker 私有网络可达，宿主机不映射。
2. **网关路由白名单**：Nginx 只代理公开路由；`/internal/runtime/...` 与 Renderer 控制面没有路由规则，外部请求在应用层被拦截。
3. **硬凭证校验**：调用 Renderer 须提供 HMAC 密钥，调用 Runtime 须验 RS256 签名；凭证缺失或为空必须 fail-closed。
4. **自动高熵生成**：单容器首启由安全随机源生成凭证，每套部署全局唯一（见 §4.2）。
5. **执行沙箱与降权**：Runtime 执行构建子进程时剥离内部认证环境变量并 `setuid/setgid` 降权，防范恶意用户代码横向刺探。

> **契约要求**：占位符拒绝清单必须覆盖交付模板实际使用的占位值。当前 `_REJECTED_ADMIN_PASSWORD_PLACEHOLDERS` 与 `_REJECTED_BUILD_CREDENTIAL_PLACEHOLDERS`（`signing_identity.py:41-53`）不包含模板里的 `REPLACE_WITH_STRONG_PASSWORD` / `REPLACE_WITH_STRONG_BUILD_CREDENTIAL`，代码默认 `Admin123456` 也不在清单内，导致「照抄模板直接上线」拦不住。修复口径见现行计划 CFG1a。

### 4.2 密钥自动生成契约

自动生成**复用既有先例**，不新造机制：`RUNTIME_RSA_PRIVATE_KEY` 已实现「ENV → 密钥文件 → `data/` 旧版密钥 → 单实例自动生成」，且多副本禁止自动生成（`config.py:100-109`、`signing_identity.py:161-211`）。按密钥性质分三类：

| 类别 | 变量 | 生成与存储 | 理由 |
| :--- | :--- | :--- | :--- |
| **必须持久化** | `AI_SECRET_ENCRYPTION_KEY` | 首启生成，落数据卷，长期不变 | 加密库内模型凭证；丢失即不可解密；轮换走 `rotate_ai_secret_key.py`；进备份集 |
| **单次启动内一致即可** | `RUNTIME_BUILD_WORKER_CREDENTIAL`<br>`RENDER_SERVICE_CREDENTIAL` | 入口脚本每次启动生成，导出给同容器子进程，**不落盘** | 单镜像下 Backend/Runtime/Renderer 同源，无需静态密钥；重启换新值不增加运维负担。留空会导致构建 Worker 不启动、任务永久 pending，因此必须生成而非省略 |
| **首启播种后失效** | `DEFAULT_ADMIN_PASSWORD` | 首启生成强随机口令，一次性写入容器日志或改为首登强制改密 | 仅用于播种管理员，之后口令哈希入库，原值不再被读取 |

统一约束：

- `BACKEND_MULTI_INSTANCE=true` 时**禁用全部自动生成**，必须显式提供实例间一致的密钥；
- 生成值不得落入任何占位符拒绝清单；
- 不得退化为镜像内固定常量；
- 数据卷复用重启后「必须持久化」类密钥保持不变；
- 缺失或非法时保持 fail-closed，不静默降级为弱密钥。

### 4.3 Lite 单镜像的故障域与隔离边界

Lite 单容器内同时运行 Backend、Runtime、Renderer（浏览器）与 Gateway 四个长期进程，属**合并故障域**；浏览器与 Backend 同文件系统与网络命名空间。在「自用 / 小团队内部」威胁模型下已接受该风险，决策与复审触发条件见[Lite 规模、故障域与隔离决策](../deployment/lite-scale-and-isolation.md) §3–§4，本文不重复其结论，也不得改写为「已具备多租户隔离」。

**Lite 面向多用户且渲染不可信页面代码时必须重开该决策**：此时 root + 无沙箱 Chromium 可读数据卷内的 SQLite 与 `/proc/1/environ` 中的密钥，属跨用户越权。

进程、代码与依赖三层边界都不受镜像合并影响：**浏览器始终由独立 Renderer 进程持有，Backend 代码不 import playwright、不在 Backend 进程内启动浏览器，且 Backend 使用的 venv 内不安装 playwright**。Lite 单镜像因此采用**双 venv 布局**（Backend venv + 独立 Renderer venv），使依赖层隔离可被静态断言而不是只写在文档里。守护点：`config.py:355-382`（遗留 `PLAYWRIGHT_*` 环境变量或 `.env` 键启动即失败）、单测 `backend/tests/unit/test_render_control_plane.py:18-24`，以及 Lite 镜像构建期断言「Backend venv 内 `import playwright` 必须失败」。合并的是镜像，不是进程；[Lite 隔离决策](../deployment/lite-scale-and-isolation.md) §3 的既有表述继续成立，无需改写。

---

## 5. 数据模型

```sql
CREATE TABLE system_settings (
    key VARCHAR(128) PRIMARY KEY,
    value JSONB NOT NULL,
    category VARCHAR(64) NOT NULL, -- storage / general / ai / security / diagnostic
    description TEXT,
    is_secret BOOLEAN DEFAULT FALSE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    updated_by INTEGER REFERENCES users(id)
);

CREATE INDEX ix_system_settings_category ON system_settings(category);
```

实现约束：

- 时间列统一使用 `app.db.types.UTCDateTime`，显式取当前时间用 `utc_now()`；历史无时区值直接补 UTC。
- 双方言（PostgreSQL / SQLite）迁移必须对拍通过；JSON 列在 SQLite 侧的存取语义与 PG 侧一致。
- `is_secret=true` 的字段**只写不读**：接口返回掩码，不回显明文；变更保留 `updated_by` / `updated_at` 审计。
- 现有公开端点 `GET /api/v1/system/settings`（`api/routes/system.py:15`，当前返回 `app_timezone`）改为读数据库覆盖层，保持「不返回凭证或其它服务端配置」的既有约束。

---

## 6. 治理后的部署模板形态

### 6.1 Lite（单镜像单容器）

镜像 `llmxpm/web-presentation:sqlite-lite` 内含 Backend、Runtime、Renderer（Chromium）与 Nginx Gateway **四个长期进程**，以及 Editor 静态资源；tini 作 PID 1 负责信号转发与浏览器孤儿回收；Python 侧为双 venv 布局（见 §4.3）：

```yaml
# 治理后的 compose.sqlite-lite.yml
services:
  platform-lite:
    image: llmxpm/web-presentation:sqlite-lite
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - lite-data:/app/backend/data
volumes:
  lite-data:
```

契约要点：

- **无 `renderer` 服务、无 `secrets:` 段、无 `depends_on`**；渲染能力来自镜像内的 Renderer 进程，不是外部容器。
- `RENDER_WORKERS_CONFIG` 使用镜像默认值（`127.0.0.1:7400`，`config.py:135-137`），单容器回环下才正确；不得沿用 `http://renderer:7400`。
- `RENDER_RUNTIME_NAVIGATION_BASE_URL` 等渲染回源基址使用容器内回环地址。
- 零必填变量：`DATABASE_URL`、`REDIS_URL`、回环通信地址、Audience 与并发预算全部由镜像 ENV 与入口脚本预置；密钥按 §4.2 自动生成。
- **验收口径是「截图与构建实际可用」**：健康接口通过、按钮可见或容器存活都不算达成。若镜像不含浏览器而模板又不启动 Renderer，结果是渲染静默不可用——这是本形态必须守住的底线。
- SQLite 单实例边界不变：Backend 单进程（禁止 `--workers>1`），不得多容器挂同一 `lite-data` 卷，并发预算固定为 1；就绪探针用 `/readyz`，`/healthz` 仅表示进程存活。

### 6.2 生产（PostgreSQL + Redis）

用户维护一个不到 10 行的 `.env`：

```ini
# 对外访问入口
BACKEND_PUBLIC_BASE_URL=https://presentation.example.com
RUNTIME_PUBLIC_BASE_URL=https://presentation.example.com/runtime
CORS_ORIGINS=["https://presentation.example.com"]
SESSION_SECURE=true

# 基础设施底座
DATABASE_URL=postgresql+asyncpg://wp_user:SecurePass123!@postgres:5432/web_presentation
REDIS_URL=redis://:SecureRedis123!@redis:6379/0

# 密钥（进备份集；多副本必须实例间一致）
AI_SECRET_ENCRYPTION_KEY=<Fernet 密钥>
DEFAULT_ADMIN_PASSWORD=<强随机口令>
RUNTIME_BUILD_WORKER_CREDENTIAL=<强随机共享凭证>
```

存储、时区、会话策略、AI 运营与诊断配置在部署成功后通过 Web UI 设置并即时生效；改动类 A 变量须重启容器（§3.3）。

`compose.prod.yml`（单 Runtime 全角色）与 `compose.runtime-roles.yml`（分角色 + 最小权限 `runtime.env` + 独立网络与资源 limits）是同一部署方式的两种规模，共用上述 `.env` 口径；分角色形态下 `runtime.env` **不得含任何平台密钥**。

---

## 7. 与其它契约文档的关系

| 主题 | 归属文档 |
| :--- | :--- |
| 批次、排期、门禁改动、重开门与验收状态 | [现行执行计划](../../temp/plans/deployment-form-and-config-governance-plan-2026-10-02.md) |
| Lite 规模、故障域与 Renderer 隔离决策 | [Lite 规模、故障域与隔离决策](../deployment/lite-scale-and-isolation.md) |
| 变量逐项说明与创建方法 | [环境变量说明](../deployment/env-vars.md) |
| 部署模板与迁移步骤 | [Compose 模板说明](../deployment/compose.md)、[生产部署指南](../deployment/README.md) |
| 多副本前提与升级排空 | [多 Backend 部署](../deployment/multi-backend.md)、[兼容矩阵](../deployment/compatibility-matrix.md) |
| AI 密钥轮换操作 | [AI 密钥轮换](../backend/ai-secret-rotation.md) |
| 用户侧快速部署 | [快速部署](../../user/quick-deployment/README.md) |

本文变更时须同步检查上述文档是否出现口径冲突；出现「文档说单容器、模板要两容器」这类不同构即为缺陷，不以未发布形态指导用户。
