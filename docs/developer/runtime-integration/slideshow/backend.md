# Backend 翻页动画与自动放映实施计划

状态：M0 已实现（WP01–WP08、WP12）；M1/M2 的 schema 2、预览权限链、媒体/演讲者能力已由 WP22/WP24/WP26/WP30 交付并开放（2026-10-18）。配置语义以[统一契约](./contract.md)为准，阶段与依赖以[总计划](./README.md)为准。

实施拆分见[工作包执行清单](./work-packages/README.md)：WP01–WP08 负责首期 Backend 和接口交付，WP22 负责媒体扩展与权限链，能力开放由阶段出口 WP12/WP21/WP30 验收。以下 B 编号继续表示上层职责，不与 WP 卡片重复计量进度。

## 1. 目标与现状

Backend 负责项目和逐页参数的完整生命周期，包括保存、校验、权限、继承、查询、产物下发和模板往返。现有路由模型及 HTTP DTO 没有动画与自动翻页字段；仅修改 Runtime 或 Editor 无法交付平台能力。

主要修改入口：

- [项目模型](../../../../backend/app/models/workspace.py)、[路由模型](../../../../backend/app/models/project_route.py)。
- [项目 DTO](../../../../backend/app/schemas/project.py)、[路由 DTO](../../../../backend/app/schemas/project_route.py)、[历史路由文档 DTO](../../../../backend/app/schemas/project_route_config.py)。
- [项目服务](../../../../backend/app/services/project_service.py)、[路由服务](../../../../backend/app/services/project_route_service.py)、[配置服务](../../../../backend/app/services/project_config_service.py)。
- [产物构造](../../../../backend/app/services/project_artifact_builder.py)、[模板包服务](../../../../backend/app/services/project_template_package_service.py)、[External 项目接口](../../../../backend/app/api/routes/external/projects.py)。

## 2. 工作包

### B01：配置 Schema、默认值和数据库迁移（M0）

- [x] 新建独立放映 Schema 与解析模块，严格处理类型、范围、完整对象和组覆盖；用共享样例固定默认值和 API/Runtime 映射。
- [x] 为项目和路由添加契约规定的 JSON 列；原始覆盖和派生生效值分离，避免重复元数据。
- [x] Alembic 迁移按 SQLite/PostgreSQL 现有适配方式执行：旧项目补默认完整值，旧叶子路由为空覆盖。
- [x] 新建项目的 default/style/custom 三种来源均由 Backend 初始化放映配置；切换工作空间样式不覆盖已有放映设置。
- [x] 明确降级边界：旧应用会忽略新增列，含放映配置的新数据与模板包不得以降级可完整保留为承诺；先备份并遵循现有迁移纪律。

验收：空库与已有项目升级后默认行为一致；非法参数无法进入数据库；两种数据库的读写和升级结果一致。

### B02：项目与路由接口（M0，依赖 B01）

- [x] 扩展创建、PATCH、详情与路由树请求/响应；读模型提供原始覆盖和只读生效值。
- [x] 在服务层统一解析继承；项目默认变更后不重写路由原始覆盖。
- [x] 路由树删除重建前按完整路径和页面绑定保存覆盖映射；实现“省略保留、null 清除、新节点继承”，处理移动、重命名、复制和重新绑定。
- [x] 解析时使用 `model_fields_set` 等机制区分未传和 null；不要先 `model_dump()` 补齐 null 后再决定写入。
- [x] 新增字段校验失败时整树不落库，沿用现有事务和权限规则；不能只保存部分合法节点。
- [x] 顶层分组禁止放映覆盖；独立叶子和分组子页采用同一规则。

验收：项目和逐页参数能够保存、重读、恢复继承；重复引用同一页面互不影响；旧客户端只调整排序不会清空已匹配节点的覆盖。

### B03：预览、构建与配置身份（M0，依赖 B02）

- [x] 在路由配置下发中生成 `transitionDefaults`、`playback` 及叶子生效组，复用同一 Backend 解析器。
- [x] 预览 artifact、构建 snapshot、发布产物和历史快照均固化同一份配置；构建执行不回读变化中的项目表。
- [x] 将新增配置纳入实际配置/产物身份和重建判断，核查现有缓存指纹；仅对影响静态截图结果的输入调整截图/检查指纹。
- [x] 旧 artifact/旧发布产物缺字段时维持兼容；新项目配置不热写已经打开的不可变预览。
- [x] Backend 模板独立维护默认值，Runtime fixture 只作本地样例和共享契约测试输入。

验收：Editor 保存后重建预览能看到新动画；同一快照在在线预览与下载构建中参数一致；历史预览不随最新项目配置改变。

### B04：模板包与复制语义（M0，依赖 B02）

- [x] 扩展模板项目摘要、项目 JSON、路由 JSON、导出收集及正式导入；预检与导入复用相同 Schema。
- [x] 包格式升级为 schema 3，同时保留 1、2、3 的导入；为旧包补默认值，为新包保留 null 和显式覆盖。
- [x] 测试导出→预检→导入→再次导出后的放映参数等价，不把 `effective_slideshow` 当作原始覆盖导入。
- [x] 只复制页面资源时不复制路由参数；整项目模板迁移时保留每次引用的参数。

验收：旧模板仍可导入；新模板跨工作空间往返不丢设置，不引入源项目 ID 或权限依赖。

### B05：External API、AI 与生成类型（M0，依赖 B02）

- [x] 对接 [CLI/MCP 计划 C01](./clients.md)，扩展外部创建、配置读取/更新、项目 PATCH 和路由树 DTO，统一字段位置。
- [x] 幂等请求指纹纳入放映对象，并区分路由字段省略和显式 null；两者写入结果不同，不能生成相同语义指纹。
- [x] 运行 Editor API 类型生成和防漂移门禁，供 Editor 使用生成模型。
- [x] 检查内容助手现有项目/路由写工具的白名单、Schema、序列化和返回摘要；若开放新参数，先修改 `tool_specs.py`，再联动指南与防漂移测试。
- [x] 自省明确支持的效果和翻页模式；不通过无约束配置字典绕过放映 DTO。

验收：内部 API、External API 与 AI 业务入口对同一输入得到相同存储结果和错误语义；未授权工作空间不能读写参数。

### B06：媒体结束模式与预览授权（M2，依赖 B03，契约先行、能力开放后置）

- [x] 先交付 `advance` 扩展 Schema、旧数据读取和预览权限适配，供 R04 实现（WP22，2026-10-18）；`media_end` 写入门禁保留到 R04/G04 验收后的 WP30。公开只读端点 `/api/system/slideshow-capabilities` 复用外部能力 builder，供 Editor 按真实能力显示表单（WP27）。
- [x] 核查并贯通 Editor→桥接宿主→Runtime 的 autoplay/fullscreen Permissions Policy；保持现有独立预览域与来源校验（WP22）。
- [x] 为预览票据到期提供可识别终态（`PREVIEW_ARTIFACT_EXPIRED` 等）；Editor 预览恢复链路消费该终态，独立窗口不自动续签，也不扩大业务 Cookie/CORS 范围。

验收：有声播放受阻能反馈；普通预览、独立窗口和捕获的权限行为一致且符合各自执行上下文。

## 3. 模块内验证与退出条件

最小测试覆盖 Schema 正反例、默认迁移、覆盖解析、整树事务、工作空间隔离、幂等指纹、产物快照和模板三版本往返。新增接口字段后必须运行类型生成与生成物防漂移；预览/构建、External/Gateway 变化按技能测试矩阵补测。

M0 退出时交付接口样例、迁移证据和产物样例，供 E01/R01/C01 联调。B06 独立交付 M2 扩展，避免首期提前披露不可执行模式。完整场景见[验收计划](./acceptance.md)。
