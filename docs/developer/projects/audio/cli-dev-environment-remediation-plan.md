# CLI 连接开发环境实测复核与改造计划

日期：2026-10-19。状态：部分实施；C01/C02/C03/C04、P01、P02、E03a、E04 已交付，E01/E02/E03b 未实施。本文保留当时的复核证据与改造方案；2026-10-25 进度以[音频总计划](README.md)为准，MCP 已移出当前交付范围。

适用仓库：`web-presentation`、`web-presentation-cli`；External 契约变化同步通知 `web-presentation-mcp`。音频字段、默认值和播放语义继续以[统一契约](../../runtime-integration/audio/contract.md)为准，本文承接 [WP19](work-packages/wp19-external-clients.md) 与 [WP20](work-packages/wp20-m2-integration.md)，不新增另一套音频契约。

## 1. 复核结论与证据边界

原实测总结对 CLI 缺口的判断基本成立，可以作为改造输入；但它证明的是部分 External API 和预览链路可用，尚不能作为“正式 CLI 音频流程通过”或 M0/M1/M2 发布验收。

本轮以主仓 `e0f4e41`、CLI 仓 `624ea31` 的当前工作树静态复核；CLI 包声明版本为 `0.3.2`。两仓均存在未提交改动，提交号只用于定位基线，不能代替实际工作树版本。未重新调用开发 API、重启服务、试听或清理测试对象，也未重跑原实测。

证据分为：用户提供的现场结果、当前代码可确认的事实、仍需新增测试的推断。原报告未附完整命令日志、浏览器版本及可移交的结果清单，不能把“实测通过”换写为本轮重新验证通过。

| 原总结 | 复核判断与必要修正 |
| --- | --- |
| 音频上传、替换、下载、hash 冲突通过 | Backend 已支持 audio；但上传绕过 Click 进入 API Client，只能算服务端/传输链路证据，不能算 `wp asset upload --type audio` 通过。 |
| `ASSET_TYPES` 缺 audio | 确认。影响 upload、list，也影响 `asset tags list --type audio`；补测不能只覆盖上传。 |
| 项目详情返回 slideshow/audio_settings 为 null | 更准确地说是 CLI 白名单省略字段。`output_profiles._pick()` 不制造 null；外部 JSON 查询工具读取不存在字段时可能显示 null。 |
| 缺项目音频专用命令 | 确认。通用 create/update/configuration 可透传，但没有 audio 子命令，也没有音频能力检查。WP19 已要求读写、清空和可读输出。 |
| 预览示例 `/overview` 在 Git Bash 被改写 | `preview.py` 的示例和 option 帮助仍带前导斜杠；CLI Skill 工作树已补 `overview` 和 `MSYS_NO_PATHCONV=1`。Shell 在启动 Python 前改写参数，CLI 无法可靠还原原值。 |
| 有构建产物接口但没有 CLI build | 确认“下载已有产物”和“发起构建”是两项能力。External 目前只有前者，CLI 两者均未交付；主仓参考文档仍有“不暴露产物下载”的过时描述。 |
| 没有资源引用查询 | External 缺少入口；内部 `AssetService.preview_asset_references()` 已覆盖页面、组件、组件版本、主题、字体及项目 cue，应复用服务。 |
| 页面 dependencies 不含音频资源名 | 确认响应只建模模块依赖，这是当前接口语义。另有内部 component-index 资源索引；应补资源依赖能力，不能把模块列表当成完整影响分析。 |
| 音频详情没有 duration | Schema 无稳定音频时长字段，当前 render metadata 主要是比例提示；缺少可供 CLI 稳定依赖的时长契约。不能靠 CLI 猜文件名、大小或字节率补值。 |
| capability=false，但写入成功，运行时只是 no-op | 写入侧缺能力门禁可由代码确认；“false 导致运行时 no-op”不成立。Runtime 按执行策略、活动窗口、绑定和静音决定是否播放，没有消费这个 External 开关。普通预览静默不能证明实际放映也被禁用。 |
| 按 screenshot_id 下载历史截图 | 新端点按内容 hash 寻址，也兼容 latest/current；不等于已提供历史截图列表、版本对应关系或保留期限。CLI 当前仍只取最新截图。 |
| Windows Renderer reload 失效而 readyz=200 | 锁文件与本地安装均为 uvicorn 0.53.0；本地 loop factory 在 Windows 的 subprocess 模式选 Selector，代码与现场原因一致。`/readyz` 仅报告进程/槽位，没有启动 Chromium 验证。 |

可定位的实现入口：

- CLI：`packages/cli/src/wp/commands/{asset,project,preview,screenshot,job}.py`、`output_fields.py`、`output_profiles.py`、`packages/api-client/src/wp_api_client/client.py`。
- Backend：[audio Schema](../../../../backend/app/schemas/audio.py)、[静态音频参数校验](../../../../backend/app/services/audio_options_gate.py)、[External 项目接口](../../../../backend/app/api/routes/external/projects.py)、[External 页面接口](../../../../backend/app/api/routes/external/pages.py)、[operation 注册表](../../../../backend/app/core/external_operations.py)。
- 引用与截图：[资源服务](../../../../backend/app/services/asset_service.py)、[页面依赖 Schema](../../../../backend/app/schemas/page.py)、[截图内容寻址](../../../../backend/app/services/screenshot_artifact_service.py)。
- 播放与探针：[Runtime cue 宿主](../../../../runtime/src/runtime-shell/audio/useAudioCues.ts)、[项目音频快照](../../../../backend/app/services/project_audio_settings_service.py)、[Renderer routes](../../../../renderer/wp_renderer/api/routes.py)。

## 2. 优先级与交付批次

P0 表示正式 CLI 当前流程被阻断；P1 表示近期正确性、契约或开发可执行性缺口；P2 表示独立增强，不全部捆绑进音频 CLI 修复。

| 编号 | 优先级 | 交付内容 | 责任仓库 | 前置/出口 |
| --- | --- | --- | --- | --- |
| C01 | P0 | audio 类型进入所有 CLI 类型选项 | CLI | 正式命令完成上传、过滤、标签查询 |
| C02 | P1 | 项目详情保留 slideshow/audio_settings | CLI | 机器可读输出与服务端值一致 |
| C03 | P1 | audio get/update/clear、统一能力检查、原子清空 | CLI + 主仓 | 先落实清空与门禁契约，再交付命令 |
| C04 | P1 | 预览路由示例跨 Shell 一致 | CLI | 帮助、Skill、README 与实测一致 |
| P01 | P1，能力开放前阻断项 | 能力声明、保存校验与执行边界一致 | 主仓 + CLI/MCP | 不靠 Skill 或普通预览静默兜底 |
| P02 | P1（本地开发） | Windows Renderer 启动默认值与执行自检 | 主仓 | 真实 render attempt 成功，产物和槽位释放 |
| E01 | P2 | 资源引用和页面资源依赖 External 查询 | 主仓 → CLI/MCP | 影响分析完整度可观察 |
| E02 | P2 | 音频时长及版本关联元数据 | 主仓 → CLI/MCP/Editor | 未知值不伪装为 0 |
| E03a | P2 | 下载已知构建任务产物 | CLI | 复用现有 External 端点 |
| E03b | P2，独立立项 | 创建/查询/等待构建任务 | 主仓 → CLI/MCP | 先补任务 External API，不能调用内部端点 |
| E04 | P2 | 按截图内容 ID 下载 | CLI | 不把内容 ID 当页面版本或任务 ID |

当时建议顺序：C01/C02/C04 形成小批交付；C03 与 P01 联合落实；P02 单独修复；再按需求交付 E01–E04。2026-10-19 当时旁白/cue 保持关闭；2026-10-25 已默认开放。

## 3. CLI 近期改造

### C01：audio 类型

- 为 `ASSET_TYPES` 加入 `audio`，覆盖 upload/list/tags list；保留未知类型的 Click 提前拒绝。
- 验证上传使用 `asset_type=audio`、扩展名和 Content-Type 正确；不增加专用上传接口，不伪装为 video。
- 替换继续携带最新 `expected_file_hash` 和 `Idempotency-Key`。409 原样呈现，不自动刷新基线后覆盖重试。
- 替换与下载复用现有实现，增加音频案例验证；服务端校验失败时不留下半条资源记录。

### C02：项目输出

- `PROJECT_DETAIL_FIELDS` 加入 `slideshow`、`audio_settings`；测试新服务端有字段时保留、旧响应缺字段时仍保持缺失，不自动补 null 或默认配置。
- `project get --json` 保留 ProjectItem 的 ID 绑定；逻辑名与状态从 configuration 查询，不为每条绑定追加请求。
- 项目列表本批保持现有字段；如后续加摘要，需由 Backend 提供稳定且批量获取的摘要，避免 CLI 拉全量 cue 或逐项目查配置。
- 同步修正 Skill 中“项目详情不保证展开音频”的过渡说明；`--raw` 继续输出原始响应。

### C03：项目音频命令

采用 `wp project audio get/update/clear`，与现有 slideshow 子命令保持一致。新命令拆到独立模块，避免继续扩大 `project.py`；复用 OpenAPI command 注册表，不另维护契约清单或离线 Schema。

| 命令（拟新增） | 行为与边界 |
| --- | --- |
| `wp project audio get <project_id>` | GET configuration，提取 audio_settings；终端展示三段音量、cue key、资源 ID/逻辑名/类型/状态/gain；JSON 输出 `{project_id, audio_settings}`。允许读取尚未开放能力的历史值，并单独提示开放状态。 |
| `wp project audio update <project_id> --audio-file <file> --idempotency-key <key>` | 文件是完整 audio_settings 对象；PUT configuration 只提交该字段。未知字段、null、缺失音量拒绝；返回采用与 get 相同的绑定摘要，可在写入后读取 configuration。 |
| `wp project audio clear <project_id> --idempotency-key <key>` | **仅清空 cue，保留三段音量及其它配置**；服务端单事务执行。音量重置不隐含在 clear 中，需要用 update 明确提交完整对象。 |

读写不能直接往返整个 GET 对象：GET 绑定包含 `asset_name/asset_type/asset_status` 等只读字段，写入仅接收 key、asset_id、gain_percent。命令不得悄悄把读模型当写模型；示例和 help 应分别展示两种 Schema。

清空的拟新增主仓契约如下；实施时先更新 operation/Schema/OpenAPI 与 API 文档，再实现 CLI：

| 项目 | 约定 |
| --- | --- |
| 请求 | `POST /api/v1/projects/{project_id}/audio-cues/clear`，无业务请求体 |
| 权限 | PAT `project:write`，校验项目访问权与工作空间归属；注册 operation `project.audio_cues.clear` |
| 幂等 | 必须提供 Idempotency-Key，沿用统一请求指纹、回放和冲突规则 |
| 执行 | 按项目事务互斥与项目音频写入共用一致边界，只删除绑定，不读出并重写音量 |
| 响应 | 200 ProjectItem，audio_settings.cue_bindings 为空，三段音量保持当前值 |
| 关闭能力时 | 仍允许清空已有绑定，便于降级治理；此例外不允许新增或恢复绑定 |

现有 API 可以提交“完整音量 + 空 cue 列表”，但若 CLI 隐式先 GET 后 PUT，会覆盖两次请求之间的音量更新。不能把幂等键当乐观锁，也不能以当前实测的单客户端成功证明并发安全。上述原子入口未交付前，clear 不标记完成；完整 update 仍可由用户明确提供载荷。

能力检查必须放在共享逻辑中，同时覆盖专用 audio update、project create/update 的 audio_settings、configuration update，不能只保护新子命令。读取项目所属 workspace 后请求 `/api/v1/workspaces/{workspace_id}/capabilities`；字段缺失、未知音频 Schema 版本或查询失败时不得推测支持。具体关闭策略见 P01。

### C04：预览路由示例

统一展示 `wp preview get --project-id <id> --route overview`；帮助说明、README、Skill 示例与分发包同步。需要保留前导斜杠时，Git Bash 使用 `MSYS_NO_PATHCONV=1 wp preview get --project-id <id> --route /overview`；单纯加引号不能视作关闭路径转换。

本项只修正示例与边界说明，API JSON 中的 `/overview` 仍合法。CLI 不识别或裁剪 `C:/Program Files/Git/...` 猜测路由。至少在 PowerShell 与 Git Bash 验证实际请求体，而不只验证 CliRunner 收到的参数。

## 4. 平台必须明确的边界

### P01：能力关闭不能仅靠客户端约定

当前 `AUDIO_OPEN_CAPABILITIES` 的注释和 WP19 实施结果主要限定“可展示/已验收的能力”；现有写入只做字段、资源归属等业务校验。因此新增硬拒绝属于**契约收紧**，应更新统一契约、WP19 测试及客户端行为，不能直接宣布原存储流程违反一个已经实现的门禁。

本计划建议统一为以下策略：

| 操作 | 能力关闭时的目标行为 |
| --- | --- |
| 上传/查询 audio、使用 content 音频 | audio_assets=true 时正常；不依赖 narration/cue 开关 |
| 读取既有旁白源码、音量、cue | 允许；返回真实存储值，明确区分“已保存”与“可执行” |
| 保存 narration 页面/组件、引入 useAudioCue | 对可识别的未开放能力依赖硬拒绝，不仅返回 warning |
| 含非空 cue_bindings 的设置写入/更新 | audio_cues=false 时拒绝；省略 audio_settings 更新其它项目属性继续允许 |
| 空 cue 设置与清理 | 允许删除绑定；明确提供完整音量的 update 仍按完整替换语义；原子 clear 只删除绑定 |
| 历史内容、新 preview/build 快照 | 按当前开放能力在受信执行配置中限制旁白/cue；普通 content 音频继续可用 |

页面/组件保存、创建/编辑 Job、模板与包导入、内部/External/AI 写入共用业务层门禁；`validate` 返回一致的能力诊断，`valid=false`，真正写入仍独立验证。候选失败用现有验证 envelope；同步 HTTP 写入建议 422、稳定业务码 `AUDIO_CAPABILITY_UNAVAILABLE`（拟新增），附 capability 与字段位置；异步 Job 使用相同业务码且不产生页面/组件新版本。

静态分析覆盖别名导入、显式与静态绑定的 purpose，复用现有解析器；动态 purpose、组件间接引用和动态加载不能仅靠正则证明完整覆盖。执行侧还要由受信配置限制未开放的自动旁白/cue，覆盖实际放映、Presenter audience 与交互预览；不能给页面一个可以自行改写的开关后宣称已隔离。

新能力输入与规则版本必须纳入 `CodeCheckFingerprintBuilder`，开关变化后不能复用旧 valid 缓存。项目 cue 资源的打包与引用仍可治理，但未开放能力不得因资源进入 manifest 而自动播放。

已创建 artifact、静态构建和旧 Runtime 版本不会因 Backend 当前开关变化而自动失效。发布时记录生成版本、过期/重建策略和无法撤回的离线产物范围；不破坏旧快照的不可变身份，不承诺 capability 是全局紧急停声开关。自动化测试可注入能力集合验证正反例，发布环境不得新增公开绕过参数。

### P02：Windows Renderer 与执行就绪

Windows 的默认 Renderer 开发启动建议关闭 uvicorn reload；显式 Proactor 方案应实测后再写成可用热重载方案。多 worker 同样可能进入 subprocess 选择分支，不能只移除 reload 就保证所有启动组合可执行。

现有 dev-start-test 工作树已记录本次排障，但命令表仍含 reload。实施时在该技能和共用启动脚本中按平台给出一致默认值，不覆盖用户已有修改，不另在 AGENTS 中复制启动细节。

增加有界启动自检：记录操作系统、实际 loop 类型与 subprocess 支持；检查浏览器可执行条件，失败时就绪返回非 200 并给稳定原因。Chromium 验证通过单槽控制器执行一次合成 attempt，遵守 per-attempt 新浏览器/Context、期限与清理约束；周期性 readyz 只读取自检结果和槽位状态，不为每次健康探针启动浏览器，也不把 busy 当不健康。

HTTP 探针通过仍不能替代端到端截图成功。最终证据需包括 attempt 终态、PNG 可读、浏览器/临时文件释放和槽位回到 idle；具体环境准备遵循 [dev-start-test](../../../../.agents/skills/dev-start-test/SKILL.md)。

## 5. 后续增强的最小契约

以下路径均为拟议，除明确注明已有端点外，不得提前写进“当前支持”的命令矩阵。

### E01：资源引用与页面资源依赖

- 优先补 `GET /api/v1/assets/{asset_id}/references`（asset:read），复用现有引用服务，External 使用严格响应 DTO，明确分页/截断、当前与组件历史版本、归档对象口径；引用对象详情还需遵循相应读取权限，不能因具有 asset:read 就泄露页面/项目身份。越权与跨 workspace 不泄露对象身份。CLI 增加 `wp asset references <id>`。
- 页面保留 `/dependencies` 的模块语义，另补 `GET /api/v1/pages/{page_id}/resource-dependencies`（page:read，涉及资产详情还需按 scope 契约约束）。CLI 增加 `wp page resource-dependencies <id>`，返回 page version、资源逻辑名、解析出的 ID/类型/状态、直接/传递来源和未解析原因。
- 项目 cue 是项目引用，不冒充页面静态依赖。组件间接资源沿既有模块/资源索引解析；动态 name 标明 unknown，构建额外资源作为独立来源，不能用空列表表达“确认无引用”。
- 引用查询是操作前快照，替换与归档写入仍由服务端再次执行现有权限和引用约束，避免查询后状态变化。

### E02：音频元数据

先定义版本化音频分析模型，再接入上传/替换/详情/包往返，建议包含 `duration_ms: int|null`、探测状态、来源及对应 file_hash。时长绑定文件版本；替换失败不污染旧值，探测失败使用 unknown/null，历史回填单独限流。

优先采用适合受支持音频格式的有界元数据解析，不把音频送进图片比例分析，也不在 Backend 启动浏览器。具体库、依赖和支持格式在实施前确定；客户端不提交一个自称可信的 duration。旁白与 timer 比较还需考虑 playbackRate、媒体起止及聚合策略；时长只能支持提示，不能证明浏览器实际播放成功。

### E03：构建下载与任务发起分开交付

E03a 复用已有 `GET /api/v1/projects/{project_id}/build-jobs/{job_id}/artifact`（project:read），新增 `wp project build artifact <project_id> <job_id> --output <zip>`，下载已知任务即可独立交付。检查 ZIP 响应、原子落盘、权限与错误；输出 project_id、build_job_id、路径、大小和本地 hash。不把本地 hash 冒充服务端可信摘要；大文件采用流式下载。

E03b 先定义 External 的创建、状态/查询与任务终态语义，再实现 `wp project build create/get/wait`。复用主仓构建服务的持久化队列与 attempt 围栏；Scope、幂等、超时、取消/重试是否支持及轮询预算必须在注册表与 OpenAPI 明确。现有 `wp job` 只管理 Mutation Job，不能把整数 build_job_id 送到 `/jobs/mutations/{id}`。

同步修正 External API 参考文档“首版不暴露产物下载”的旧结论，以及 CLI 能力矩阵；在 E03b 完成前仍写明“不能从 CLI 发起构建”。没有 CLI build 并不免除 WP06/WP20 的独立构建产物验收，可使用平台已有入口生成并验证产物。

### E04：按内容身份下载截图

给现有 `wp page screenshot <page_id>` 增加可选 `--screenshot-id <hash>`，指定时调用已有 `/api/v1/pages/{page_id}/screenshots/{screenshot_id}/content`（page:read），只下载、不刷新页面截图；未指定时保留最新截图流程及其 page:read + preview:run 要求。

内容 ID 是页面范围内的 SHA-256，latest/current 是可变别名。CLI 不沿用最新截图接口独有的 X-Page-Version-No 校验到历史内容端点，不用当前页面版本给旧图命名；输出 screenshot_id 与 ETag/hash，无法获知历史 version_no 时省略或明确未知。旧对象不存在时呈现 404，不回退最新图；历史枚举和保留策略另行定义。

## 6. 验证与发布出口

实施按 [测试矩阵](../../../../.agents/skills/dev-start-test/references/testing-matrix.md) 选取最小充分测试，不为验证重启健康开发服务，不用开发库执行 E2E reset。

| 批次 | 必要自动化与真实流程 |
| --- | --- |
| C01/C02/C04 | CLI command/output/preview 单测、相邻 Backend OpenAPI 注册契约对拍；audio 上传→过滤→替换→下载 hash、旧 hash 冲突；PowerShell/Git Bash 路由请求体验证 |
| C03/P01 | 音频命令读写模型、能力缺失/false/true、通用命令绕过防护；Backend audio/External API/静态参数/源码写 Job 测试；原子 clear 与并发音量更新、幂等回放、scope/跨空间/非 audio/归档/重复 key/部分对象/null/省略语义；能力变更导致校验缓存失效 |
| P01 Runtime | 实际放映/Presenter audience 的关闭能力用例，普通预览与 capture 静态隔离；启用组合验证真实播放，关闭组合不能只断言“没听见” |
| P02 | Renderer 单测及 Windows 有/无 reload 的自检失败/成功；真实 Backend→Renderer→Runtime 截图及进程、槽位、产物清理 |
| E01/E02 | 引用服务和 External 权限/DTO、组件历史/动态引用、不完整标记；多格式时长、坏文件、未知值、替换与历史版本一致性 |
| E03/E04 | API-client 二进制/流式传输、同源 PAT 防护、错误响应不写假文件；构建任务与 Mutation Job 分离；旧截图 ID 不回退最新、无版本头可下载 |

HTTP DTO 变更运行 Editor API codegen 与 generated 防漂移；External 路径/Scope/Schema 变化补 Gateway、CLI Skill 与跨仓契约验证。CLI 仓执行自身 AGENTS 的单测、wheel 构建和 Skill 分发校验；相邻 Backend 契约缺失导致 skip 需作为发布缺口报告。

每批记录主仓/CLI 提交与工作树差异、安装包版本、命令、通过/失败/跳过数量、未运行项；CLI 帮助使用当前 Backend OpenAPI，失败不回退离线契约。MCP 后续适配单独记录，不因其未交付保留 WP19/WP20 未完成状态。

真实声音验收仍按[音频验收计划](acceptance.md)：手动播放、autoplay blocked、Range/seek、旁白起止与 generation、单一播放窗口、切页/点击 cue、静音、长稳和离线构建。截图只能确认界面渲染，不能证明可听、自动旁白或 cue 播放。不得用本次两页截图或 API Client 绕行替代阶段门禁。

## 7. 现场对象与本轮文档验证

原实测保留工作空间 43、项目 130、页面 698/699、音频资源 505；这些 ID 仅供定位现场，不能写死进自动化测试或当作后续必然存在的 fixture。本轮未访问或更改其状态，清理不属于本次任务。

原报告称载荷、截图和下载位于 `.tmp/web-presentation`。本轮在主仓该目录确认了音频、下载文件、Vue/JSON 载荷，但未发现 page-698.png/page-699.png；CLI 仓对应目录也未列出文件。截图位置仍需原执行方补充，不能写成已归档证据。临时产物不提交仓库。

后续现场报告补齐：实测时间、安装包与代码版本、服务地址/版本组合、浏览器/Shell、完整命令及退出码、响应摘要、素材来源与 hash、截图实际路径和未运行项；移交报告去除 PAT 和短期票据。

本轮仅新增改造文档与导航，实际验证：

- `pnpm run test:repository`：测试启动前被 pnpm 自动依赖检查中止（`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`），未计为测试失败，也未执行依赖重装。
- `pnpm --config.verify-deps-before-run=false run test:repository`：使用现有依赖执行，8 个文件、61 项测试全部通过，包含相对文档链接与代码围栏校验。
- `git diff --check`：通过。

未执行产品改造、原实测复跑、完整 E2E 或声音验收，本轮纯文档改动不需要运行这些门禁；WP06/WP12/WP20 的验收状态保持不变。

## 8. 实施状态（2026-10-19）

| 批次 | 状态 | 落地内容 |
| --- | --- | --- |
| C01 | 已交付 | CLI `ASSET_TYPES` 增加 `audio`，覆盖 upload/list/tags list；音频上传显式声明受支持 Content-Type |
| C02 | 已交付 | `PROJECT_DETAIL_FIELDS` 保留 `slideshow`、`audio_settings`；旧响应缺字段不补 null |
| C03 | 已交付 | 主仓新增 `project.audio_cues.clear` 原子清空接口；CLI 新增 `project audio get/update/clear` 与统一能力门禁 |
| C04 | 已交付 | 预览帮助、README 与 Skill 默认使用 `--route overview`，Git Bash 例外单列 |
| P01 | 已交付（不含 Runtime 实机放映用例） | 能力门禁覆盖项目 cue、模板导入、页面/组件旁白与 useAudioCue；validate 同码；指纹纳入能力；新快照裁剪 cue |
| P02 | 已交付 | Renderer 启动自检（OS/loop/subprocess/Chromium 实际启动），readyz 失败非 200；本地启动默认关闭 reload |
| E03a | 已交付 | `wp project build artifact` 流式下载、原子落盘、本地 SHA-256；不冒充服务端摘要 |
| E04 | 已交付 | `wp page screenshot --screenshot-id` 按内容 ID 下载，不回退最新图、不猜测页面版本 |
| E01 | 未实施 | 资源引用与页面资源依赖 External 查询 |
| E02 | 未实施 | 音频时长与版本关联元数据 |
| E03b | 未实施（独立立项） | 构建任务创建/查询/等待 External API |

验证边界：

- 主仓：音频 External/契约、能力门禁、页面/组件保存、构建与预览快照、代码检查指纹、Renderer 启动自检测试通过。
- CLI 仓：除跨仓 Backend OpenAPI 对拍外的单测、wheel 与 Skill 分发校验通过；跨仓对拍与真实上传→绑定→替换→清空流程未复跑。
- 未执行：Runtime 实际放映/Presenter audience 的能力关闭用例、真实截图端到端与声音验收。P01 的“执行边界一致”目前覆盖 Backend 门禁与新快照裁剪，不包含已生成 artifact 的撤回。
