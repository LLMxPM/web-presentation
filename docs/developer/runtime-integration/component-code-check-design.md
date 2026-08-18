# 面向智能体的组件 Check 体系设计

## 1. 文档目的

本文基于当前页面 check、组件预览和 AI 组件工具链，设计一套主要服务于智能体的组件反馈机制。

目标不是在 Editor 再建设一套面向用户的“检查”产品。用户已经可以通过组件预览查看效果和错误；本方案重点解决智能体创建或修改组件后，如何自动获得足够准确、可操作的反馈，并继续修复，直到候选组件能够运行、真实渲染且不存在明显布局问题。

本文同时记录设计边界与实施状态。核心智能体闭环已落地；缓存、更多兼容性 profile 和高级布局规则仍属于后续增强。

### 1.1 当前实施状态

截至 2026-08-10，已经落地：

- 正式 `ComponentValidationResult` Pydantic 结果契约，以及 contract/compile/render 阶段状态。
- `ComponentValidationService` 编排、候选 hash、基础设施 unavailable/retryable 分类和 artifact 清理。
- 页面/内容/原子组件各自的版本化临时 validation profile，不读取 AI 当前焦点项目尺寸和基础字号。
- Runtime 组件预览 `render-settled` 协议、默认态与最多 10 个 presets 的真实浏览器检查。
- setup/render/pageerror/console error、视觉资源未就绪、空白、完全越界、水平/垂直溢出和裁切诊断。
- `validate_entity(component.check)` 独立只读调用，以及新建组件、源码 edits、`previewSchema`/组件类型更新的自动写入前 check。
- 源码与 schema/type 写入在耗时检查后的基线复核，防止检查期间草稿变化。

尚未落地：

- candidate hash 的短期结果缓存和持久化校验任务。
- 面向具体项目页面配置的 contextual component check；当前仍由页面 check 承担最终集成验证。
- 多基础字号 compatibility profiles、内容组件尺寸控制响应差值和 preset 残留状态等低置信度规则。
- Editor 专用 check 交互；这不属于当前目标。

## 2. 范围与结论

### 2.1 本次覆盖范围

组件智能体的以下三类写操作必须自动 check：

1. 新建组件：同时检查候选源码、组件类型和 `previewSchema`。
2. 修改组件源码：基于当前组件元数据和候选源码检查。
3. 修改组件 `previewSchema`：基于当前源码和候选 schema 检查。

同时，组件 check 应继续作为 `validate_entity(component.check)` 的只读能力对模型开放，使智能体可以像检查页面一样，在不发生写入的情况下单独检查当前组件或一份完整候选。

一次完整 check 需要回答三个问题：

- 代码能不能跑起来：契约、依赖、Vue/Vite 编译是否通过。
- 组件能不能实际渲染：组件预览宿主页是否启动，默认态和预设场景是否产生运行时异常。
- 渲染后的布局有没有明显问题：是否空白、零尺寸、超出预览容器、被裁切或出现与组件类型不匹配的尺寸行为。

这里的渲染环境不属于组件数据。页面尺寸、项目基础字号和项目视觉配置只能作为本次 check 的临时上下文，不能写入组件或 `previewSchema`，也不能默认继承 AI 会话当前焦点项目。

### 2.2 明确不纳入主线

- 不新增 Editor “检查”按钮、检查面板或保存门禁。
- 不改变用户现有的保存、预览和查看报错流程。
- 不把发布校验、组件列表健康状态、检查任务持久化作为本轮必需项。
- 不对每次用户键盘输入执行 Runtime check。
- 不用截图像素差作为通用正确性标准。

### 2.3 核心结论

当前组件已经具备候选源码的 Runtime/Vite 编译 check，但缺少浏览器真实渲染和布局诊断；同时，自动 check 只接入了 AI 结构化源码编辑，没有完整覆盖 AI 新建组件和修改 `previewSchema`。

建议复用现有 `CodeCheckService`、`ComponentPreviewService`、Runtime diagnostics 工作区池和共享 Playwright 池，增加组件渲染诊断层，并由三类 AI 写工具和 `validate_entity(component.check)` 复用同一个校验内核。写工具在真正写入前必须自动调用；`validate_entity` 提供按需只读检查。内部 check 结果先经过共享格式化层，再让模型根据稳定诊断码、场景和受控 facts 重试。

## 3. 当前体系梳理

### 3.1 页面 check 可复用的链路

页面 check 当前已经形成以下链路：

```mermaid
flowchart LR
    A["候选页面源码"] --> B["Backend 边界校验"]
    B --> C["生成临时 preview artifact"]
    C --> D["Runtime/Vite 编译诊断"]
    D -->|"通过"| E["共享 Playwright 池真实渲染"]
    E --> F["运行时与布局诊断"]
    D -->|"失败"| G["结构化错误"]
    F --> H["返回调用方"]
    G --> H
    H --> I["清理临时 artifact"]
```

对应职责主要位于：

| 能力 | 当前实现 | 可复用点 |
| --- | --- | --- |
| 候选源码与 edits | `CodeCheckService` | 生成待检查候选，不先写业务数据 |
| 完整模块图 | `PreviewService` / `ComponentPreviewService` | 注入项目配置、组件依赖和 Runtime Kit |
| 编译诊断 | `RuntimeDiagnosticsClient` | 使用隔离工作区执行 Vite build |
| 浏览器诊断 | `PageRenderDiagnosticsService` | 共享 Playwright 池、资源等待和错误采集模式 |
| 临时资源回收 | check 编排层 | 结束后清理 artifact，TTL 兜底 |

组件不应另起一套构建器或浏览器进程池，但布局规则不能直接照搬页面固定画布规则。

### 3.2 组件已经具备的校验

Backend 当前已有同步契约校验：

- 只支持 Vue 组件文件。
- `import_name`、名称和组件类型等基础字段校验。
- `previewSchema` 根节点必须是 JSON 对象。
- slot/preset 中的组件引用必须满足版本化 Runtime Kit 或工作空间组件约束。
- 内容组件必须声明尺寸控制字段。
- 组件依赖必须存在，且不能形成循环依赖。
- 发布时维护依赖、资源和 fingerprint 索引。

`CodeCheckService.check_component_code` 当前还支持：

- 检查已有组件当前源码、完整候选源码或结构化 edits。
- 检查尚未创建的临时组件候选。
- 使用候选 `preview_schema` 覆盖当前值。
- 创建组件预览 artifact，并执行 Runtime/Vite 编译诊断。
- 返回 canonical diff，结束后清理临时 artifact。

Runtime 组件预览页已经能够：

- 根据 `previewSchema` 构造默认 props、slots、mocks 和 presets。
- 实际加载组件和相关依赖。
- 通过 `component-preview:ready` / `component-preview:error` 报告启动结果。
- 接收状态更新并切换预览场景。

### 3.3 AI 写操作当前缺口

| AI 操作 | 当前状态 | 缺口 |
| --- | --- | --- |
| 新建组件 | 直接创建草稿 | 没有自动 Runtime check |
| 修改组件源码 | `apply_component_edits` 写入前自动 compile check | 没有真实渲染和布局诊断 |
| 修改 `previewSchema` | 元数据更新后直接保存 | 没有验证新 schema 能否驱动真实预览 |
| 独立 `validate_entity(component.check)` | 可由模型主动调用 | 依赖模型记得调用，不能保证写操作闭环 |

这与 `tool_specs.py` 中“组件创建、源码更新会自动校验”的描述存在漂移。更重要的是，Vite 编译通过并不表示组件能够在预览宿主页中正常执行，也不能证明默认 props、slots 或 presets 下的布局可用。

## 4. 目标执行模型

### 4.1 三层诊断

| 阶段 | 要回答的问题 | 主要检查 | 执行环境 |
| --- | --- | --- | --- |
| contract | 候选输入是否符合平台契约 | 字段、schema 结构、导入边界、依赖存在性、循环依赖、组件类型约束 | Backend |
| compile | 完整组件图能否构建 | Vue SFC、TypeScript、模块解析、Runtime Kit 与工作空间依赖 | Runtime diagnostics |
| render | 候选组件的实际结果是否可用 | 宿主页启动、运行时异常、默认态/presets、资源加载、布局事实 | Runtime preview + Playwright |

执行顺序固定为 `contract → compile → render`。前一阶段出现 error 后立即停止，避免把编译错误包装成渲染超时，也避免无效消耗浏览器资源。

### 4.2 三类写操作的候选组合

| 写操作 | 源码候选 | `previewSchema` 候选 | 组件其他信息 | 通过后写入 |
| --- | --- | --- | --- | --- |
| 新建组件 | 工具请求中的完整源码 | 工具请求中的完整 schema | 工具请求中的名称、类型、引用名 | 创建组件草稿 |
| 修改源码 | 应用 edits 后的完整源码 | 当前草稿 schema | 当前草稿元数据 | 只保存源码变更 |
| 修改 schema | 当前草稿源码 | 工具请求中的完整候选 schema | 当前草稿元数据 | 只保存 schema 变更 |

检查必须针对最终要写入的完整候选快照，不能分别检查一个源码片段或局部 schema。候选未通过时不写入，现有数据保持不变；模型下一轮可根据诊断重新提交完整创建参数、修订后的 edits 或修订后的 schema。

### 4.3 自动反馈闭环

```mermaid
flowchart TD
    A["模型调用组件写工具"] --> B["工具组装完整候选快照"]
    B --> C["contract check"]
    C -->|"error"| H["返回结构化诊断，不写入"]
    C -->|"passed"| D["compile check"]
    D -->|"error"| H
    D -->|"passed"| E["render + layout check"]
    E -->|"error"| H
    E -->|"passed / warnings"| F["执行组件写入"]
    F --> G["返回写入结果和校验摘要"]
    H --> I["模型根据 code、场景和建议修复"]
    I --> A
```

组件 check 对模型提供两个入口，但只有一个校验实现：

- 自动入口：三类写工具在提交写入前强制执行，保证模型漏掉预检也不会写入坏候选。
- 独立入口：`validate_entity(component.check)` 按模型需要执行只读检查，用于检查当前组件、试验完整候选或在修复过程中确认结果。

独立入口不应成为三类写操作正确性的前置要求。模型已经通过 `validate_entity` 检查过候选后，写工具原则上仍需校验；后续可以依据相同 `candidate_hash`、Runtime 版本和规则版本复用短期结果，避免重复消耗 Runtime/浏览器资源。

## 5. 真实渲染检查设计

### 5.1 检查场景

一次组件渲染 check 使用显式 `scenarios`：

- `default`：根据 `previewSchema` 默认值生成，必须检查。
- `preset:<key>`：按 preset 合并 props、slots 和 mocks。
- 默认态与 presets 状态经过规范化 JSON hash 去重。
- 首期最多检查默认态加 10 个 preset；超限返回 warning，并在结果中列出未检查数量。
- 任一已执行场景出现运行时 error，则候选整体失败。

首期不自动组合所有 prop 边界值，也不随机 fuzz。只有 `previewSchema` 明确描述的状态，才是智能体能够理解和定向修复的稳定场景。

### 5.2 浏览器执行步骤

组件专用 `ComponentRenderDiagnosticsService` 建议按以下步骤工作：

1. 使用 compile 阶段同一个临时 artifact 打开组件预览宿主页。
2. 等待版本化的预览握手；收到 `component-preview:error` 立即记录 error。
3. 监听 `pageerror`、未处理 Promise rejection、控制台 error 和关键资源失败。
4. 等待字体、图片及 Runtime 已知视觉资源进入稳定状态。
5. 检查 `default`，再通过现有状态更新协议逐个切换 preset。
6. 每次切换等待一次明确的 `render-settled` 信号；若当前协议没有该信号，应先扩展协议，不能依赖固定 sleep。
7. 每个场景读取 DOM 几何事实并执行对应组件类型的布局规则。
8. 汇总结果后关闭页面，并由外层统一清理 artifact。

所有浏览器任务必须接入现有共享 Playwright 池和有界队列，不允许每次 check 自行启动 Chromium。

### 5.3 运行时错误

以下情况应作为阻断 error：

- 预览宿主页未能进入 ready，或明确进入 error。
- 组件 `setup`、render、computed、watch 或事件初始化产生未处理异常。
- 动态 import 或关键组件依赖加载失败。
- 默认态或某个 preset 无法完成稳定渲染。
- 根节点完全不存在，或存在但没有任何可见内容。

普通 console warning 不直接阻断。console error 需要过滤 Runtime 自身已知噪声，并保留来源 URL、场景和消息；无法确定属于候选组件的错误先作为 warning，避免误导模型。

### 5.4 布局规则

布局诊断应提供“事实 + 判定 + 修复方向”，不能只返回“布局有问题”。首期建议覆盖高置信度规则：

| 规则 | 默认级别 | 适用范围 | 需要返回的事实 |
| --- | --- | --- | --- |
| 根节点不可见或有效面积为 0 | error | 全部组件 | 根节点数量、宽高、可见性 |
| 内容完全在预览 frame 外 | error | 全部组件 | 根节点 rect、frame rect、相交面积 |
| 水平或垂直明显溢出 | warning | 内容/原子组件 | 溢出方向、像素值、发生溢出的节点摘要 |
| 内容被 `overflow: hidden` 明显裁切 | warning | 内容/原子组件 | scroll/client 尺寸、裁切祖先 |
| 页面组件超出目标画布 | warning | 页面组件 | 四边超出像素、目标画布尺寸 |
| 内容组件不响应声明的尺寸控制 | warning | 内容组件 | 输入尺寸与实际根节点尺寸 |
| preset 切换后残留旧内容或尺寸不稳定 | warning | 全部组件 | 切换前后节点/尺寸事实；首期可延后 |

布局判断需要区分组件类型：

- 页面组件按项目画布尺寸检查，关注整体越界和画布覆盖。
- 内容组件在 placement frame 中检查，重点验证 `previewSchema` 声明的尺寸控制是否生效。
- 原子组件允许内容自适应，不要求铺满 frame，只检查不可见、完全越界和明显裁切。

布局问题默认使用 warning，只有“没有可见结果”或“完全在容器外”等确定无法使用的情况才是 error。这样模型能获得反馈并主动改进，同时避免启发式布局规则过度阻断有效组件。

### 5.5 页面尺寸与基础字号的处理

组件是工作空间共享资产，不天然属于某个项目，因此页面宽高、`base_font_size`、图标默认描边和项目主题不能成为组件校验输入中的隐含组件属性。同一个候选组件不能因为智能体当前焦点切换到另一个项目，就得到不同的基础校验结论。

现有 `ComponentPreviewOptions.page` 已经能够在创建 preview artifact 时临时注入宽、高、基础字号、图标描边和主题；这正是校验环境的承载位置。建议把它正式定义为执行期 `validation_profile`，只存在于一次 check 的 artifact 中：

```json
{
  "profile_key": "component-content-default.v1",
  "viewport": {"width": 1440, "height": 900},
  "page": {
    "width": 1920,
    "height": 1080,
    "base_font_size": "20px",
    "icon_default_stroke_width": 2,
    "theme_source": "workspace-default"
  },
  "placement": {
    "width_mode": "fixed",
    "width_value": 960,
    "height_mode": "auto",
    "padding": 48
  }
}
```

示例数值是校验 fixture，不是新的组件字段；最终数值应由现有平台默认值和真实组件样本确定。profile 必须有版本号，Backend 与 Runtime 共同维护其含义。

#### 固定校验环境与真实项目环境的边界

- 基础组件 check 使用平台定义的稳定 profile，保证同一候选在相同 profile、主题 fingerprint、Runtime 和规则版本下结果可重复。
- 不读取 AI run 的 `project_id`、当前项目页面尺寸或基础字号作为默认值。
- 不把 `page.width`、`page.height` 或 `base_font_size` 加入组件模型、组件版本或 `previewSchema`。
- 工作空间默认主题可以作为资源和 CSS token 的执行依赖，但诊断结果要记录实际使用的主题 key/fingerprint；主题变化后缓存失效。
- 如果未来需要回答“这个组件放进某个具体项目是否合适”，应增加显式的 contextual check，或由页面 check 在真实项目 artifact 中验证；它不能替代组件的稳定基础 check。

#### 不同组件类型如何使用 profile

| 组件类型 | 校验基准 | 页面尺寸/字号的角色 |
| --- | --- | --- |
| 原子组件 | 自身可见区域和 placement frame | 仅提供 CSS 继承与可用宿主空间，不要求填满页面 |
| 内容组件 | `previewSchema` 默认尺寸 props + placement frame | 用于验证尺寸控制、溢出和裁切，不把 frame 当组件固有尺寸 |
| 页面组件 | profile 提供的完整画布 | 在代表性画布中检查覆盖、越界和运行时结果，但不声明组件只支持该画布 |

基础字号也应视为环境变量：Runtime 在宿主页设置与真实页面一致的 CSS 变量和继承字号，组件 check 验证组件是否能在该环境中运行。首期使用一个必需的基准字号 profile；后续若真实组件存在明显的字号缩放问题，可以增加一个有界的 typography compatibility profile，而不是遍历任意字号。

#### 结果语义

每个 scenario 结果都需要增加 `profile_key`，顶层结果记录 `validation_profile_version`。模型收到布局反馈时，应能看出问题发生在哪个临时环境，例如“在 `component-content-default.v1` 的 960px placement frame 下右侧溢出 28px”。

组件 check 的结论应表述为“候选在已执行的校验 profile 下通过”，不能表述为“在所有页面尺寸和字号下都正确”。当组件进入具体页面后，页面 check 仍负责基于真实项目尺寸、基础字号、主题和页面组合关系发现集成问题。

## 6. 面向模型的结果契约

### 6.0 内部完整结果与模型侧精简结果

`CodeCheckService`、`ComponentValidationService` 和 Runtime 之间继续使用下文的完整 `ComponentValidationResult`，其中可以保留完整 `diagnostics`、`scenarios`、`facts` 和布局分析，供内部编排、日志与契约测试使用。共享格式化层只在 AI 工具返回模型前执行，不改变这些内部结果，也不修改 Runtime 诊断协议。

写入/修改工具只把校验部分转换为短文本，保留对象 ID、版本、`success`、`applied`、hash 和 `canonical_diff` 等业务字段；不会回传原始 `diagnostics`、完整 `layout_analysis`、全量 scenario 或重复的 validation。warning/error 合计最多返回 10 条，超出部分标记省略数量。

`validate_entity` 的页面/组件 check 返回短文本而非结构化完整结果：`detail=false` 保留摘要、code、message、定位以及组件的 scenario/profile；`detail=true` 仍最多返回 10 条问题，并增加受控 facts 和布局数值。两种模式都不返回正常布局项、完整浏览器几何数据或原始 JSON 清单。资源差异预览继续使用现有结构化 envelope。

### 6.1 顶层结果

建议新增正式 Pydantic Schema，供三类 AI 写工具共用：

```json
{
  "schema_version": 1,
  "target": {
    "kind": "component",
    "operation": "update_preview_schema",
    "component_id": 42,
    "candidate_hash": "sha256:..."
  },
  "validation_profile_version": "component-profiles.v1",
  "status": "failed",
  "valid": false,
  "retryable": false,
  "summary": "组件可以编译，但 preset:compact 渲染时发生异常。",
  "stages": {
    "contract": "passed",
    "compile": "passed",
    "render": "failed"
  },
  "diagnostics": [],
  "scenarios": [],
  "canonical_diff": null
}
```

状态固定为：

- `passed`：所有阶段完成，无 warning/error。
- `passed_with_warnings`：没有 error，但存在可改进问题。
- `failed`：候选组件自身存在阻断错误。
- `unavailable`：Runtime、浏览器池或诊断基础设施不可用，`retryable=true`，不能归因于候选组件。

`valid` 表达候选是否允许写入；`retryable` 告诉智能体是否应原样重试。基础设施不可用时不应让模型修改源码碰运气。

### 6.2 单条诊断

```json
{
  "severity": "warning",
  "stage": "render",
  "source": "component-layout",
  "code": "COMPONENT_RENDER_HORIZONTAL_OVERFLOW",
  "message": "preset:compact 中内容向右超出预览 frame 28px。",
  "scenario_key": "preset:compact",
  "profile_key": "component-content-default.v1",
  "location": null,
  "facts": {
    "overflow_right_px": 28,
    "frame_width_px": 320,
    "root_width_px": 348,
    "selector_hint": ".feature-card"
  },
  "suggestion": "检查根容器固定宽度、padding 与 box-sizing；优先让组件宽度响应 placement frame。"
}
```

给模型的字段需要满足：

- `code` 稳定，模型提示和测试不依赖完整中文文案。
- `scenario_key` 指明问题发生在默认态还是某个 preset。
- `facts` 返回测量事实，帮助模型判断根因。
- `location` 只有 Runtime 能可靠提供文件、行、列时才填写，不能伪造。
- `suggestion` 给出排查方向，不自动声称唯一修复方案。
- 编译日志先规范化和截断，去掉本机绝对路径、重复堆栈和无关 Vite 噪声。

### 6.3 建议诊断码

| source | code | 默认级别 |
| --- | --- | --- |
| `backend-contract` | `COMPONENT_PREVIEW_SCHEMA_INVALID` | error |
| `backend-dependency` | `COMPONENT_DEPENDENCY_INVALID` | error |
| `runtime-compile` | `COMPONENT_COMPILE_FAILED` | error |
| `component-render` | `COMPONENT_PREVIEW_BOOTSTRAP_FAILED` | error |
| `component-render` | `COMPONENT_RENDER_RUNTIME_ERROR` | error |
| `component-render` | `COMPONENT_RENDER_EMPTY` | error |
| `component-render` | `COMPONENT_RENDER_ASSET_NOT_READY` | warning |
| `component-layout` | `COMPONENT_RENDER_OUTSIDE_FRAME` | error |
| `component-layout` | `COMPONENT_RENDER_HORIZONTAL_OVERFLOW` | warning |
| `component-layout` | `COMPONENT_RENDER_VERTICAL_OVERFLOW` | warning |
| `component-layout` | `COMPONENT_RENDER_CLIPPED` | warning |
| `component-layout` | `COMPONENT_SIZE_CONTROL_MISMATCH` | warning |
| `component-check` | `COMPONENT_CHECK_SCENARIOS_TRUNCATED` | warning |
| `infrastructure` | `COMPONENT_CHECK_UNAVAILABLE` | 顶层 unavailable |

## 7. 写工具接入策略

### 7.1 新建组件

新建工具先组装完整的临时组件描述，包括源码、`previewSchema`、组件类型、引用名和依赖上下文，再创建 source preview artifact。

- check failed：不创建草稿，工具返回 `applied=false` 和精简 validation 文本；完整 validation 只保留在 Backend 内部。
- check unavailable：不创建草稿，返回 `retryable=true`，由智能体稍后原样重试。
- passed 或 passed_with_warnings：允许创建；warnings 随成功结果返回，提示模型是否需要继续优化。

新建失败时没有 `component_id`，结果使用请求级 `candidate_hash` 关联同一候选即可。

### 7.2 修改组件源码

沿用现有 `apply_component_edits` 的候选 diff 机制，但把 check 从仅 compile 升级为完整三层：

1. 读取当前组件快照。
2. 应用结构化 edits，得到完整候选源码和 canonical diff。
3. 使用当前 `previewSchema` 执行完整 check。
4. 通过后，在写事务中复核原始源码 hash/版本，避免检查期间发生并发修改。
5. 写入成功后返回 canonical diff、validation 短文本和 warnings。

失败时不保存 edits，模型根据诊断重新生成 edits；不应把失败候选写成草稿再让模型修复。

### 7.3 修改 `previewSchema`

schema 修改不是普通元数据更新，应从通用组件元数据写工具中拆出明确的候选校验路径，或在检测到 `preview_schema` 字段时进入同一校验编排。

检查使用“当前源码 + 候选 schema”，必须实际渲染 default 和 presets。这样可以发现 JSON 结构合法但默认值类型错误、slot 内容异常、mock 缺失、preset 运行时报错或尺寸 placement 不合理等问题。

检查通过后仅写 schema，并在事务内复核当前源码和旧 schema 的 candidate 基线；否则可能把针对旧源码验证过的 schema 写到已经变化的组件上。

### 7.4 工具返回封装

三类工具保持一致的业务返回语义；其中 `validation` 是模型侧精简短文本，完整结果只在 Backend 内部保留：

```json
{
  "success": true,
  "applied": false,
  "operation": "create_component",
  "component": null,
  "validation": "检查结论：failed\n摘要：组件未创建：默认场景渲染失败。\n错误：\n- [COMPONENT_RENDER_EMPTY] default 没有可见的组件根内容。\n下一步：如需查看诊断明细，请调用 validate_entity，并设置 detail=true。"
}
```

这里 `success=true` 表示工具按预期完成，`applied=false` 表示业务写入未发生；不要把候选校验失败伪装成工具执行异常。只有权限、参数协议或内部未处理错误才走工具异常路径。

AI 系统提示应明确：

- `validation` 中出现 error/warning 时，根据 code、message、定位、scenario 和 profile 修改候选；需要更多上下文时，对相同目标和候选调用 `validate_entity(detail=true)`。
- `unavailable` 或提示基础设施不可用时：不要修改候选，稍后原样重试或向用户说明暂不可检查。
- `passed_with_warnings`：写入已经发生；判断 warning 是否影响用户目标，必要时继续修改。

### 7.5 `validate_entity(component.check)` 独立入口

`validate_entity` 中的组件检查应与页面检查保持一致的按需调用能力，并支持以下目标：

| 模式 | 输入 | 用途 |
| --- | --- | --- |
| current | `component_id` | 重新检查当前已保存组件的源码和 schema |
| content | 完整候选源码，可选候选 `preview_schema` | 在修改前试验一份完整源码候选 |
| edits | `component_id` + 结构化 edits，可选候选 `preview_schema` | 预检基于当前源码形成的编辑结果 |
| transient | 创建所需的工作空间、源码、schema、类型等完整候选信息 | 在尚无 `component_id` 时预检新组件 |

调用结果返回与写工具一致的精简校验文本，但额外明确：

- `applied=false` 固定成立，调用不会创建或修改组件。
- 写工具之外，仍可从问题文本读取 code、message、定位、scenario/profile；使用 `detail=true` 时读取受控 facts 和布局数值。内部完整结果仍保留 `candidate_hash`、`validation_profile_version` 和 canonical diff，便于日志与服务端确认具体候选与环境。
- 默认执行 contract、compile、render 全部阶段，不允许模型只执行 render 而跳过依赖阶段。
- warning、failed 和 unavailable 的语义与自动入口完全一致。
- 临时 artifact 在调用结束后清理，不能把 artifact ID 当成持久检查记录。

工具说明应告诉模型何时值得单独调用：诊断当前组件、在大幅修改前预检、验证一个候选 schema，或确认修复是否消除了 warning。工具说明也要明确：直接调用三类写工具时无需先调用 `validate_entity`，因为写工具会自动执行同一检查。

## 8. 服务与协议边界

建议新增 `ComponentValidationService` 作为编排层，职责为：

- 接收规范化的完整候选快照，而不是依赖某一种 AI 工具参数。
- 顺序执行 contract、compile 和 render。
- 统一状态、诊断码、场景摘要和 `candidate_hash`。
- 确保浏览器页面和临时 artifact 始终清理。

既有能力保持各自边界：

- Backend 契约与依赖服务继续作为平台规则的单一事实源。
- `ComponentPreviewService` 负责为未保存候选创建完整 artifact。
- `RuntimeDiagnosticsClient` 负责 compile，不决定是否写入。
- 新增 `ComponentRenderDiagnosticsService` 负责浏览器运行与布局事实。
- AI 写工具负责写入前调用、并发复核和把结果反馈给模型。
- Runtime 预览协议提供 `ready/error/render-settled` 和场景切换能力，不承载 AI 工具语义。

不建议为首期新增公开 Editor REST check 接口或持久化 validation job。校验先作为 Backend 内部应用服务供 AI 工具调用；如果未来有其他调用方，再在不改变核心结果 Schema 的前提下暴露接口。

## 9. 分阶段落地计划

### 阶段一：统一 AI 写入前的编译反馈（已完成）

目标是消除当前三类写操作的接入不一致，并先建立稳定返回契约。

- 定义组件候选、校验结果、diagnostic 和 scenario 的 Pydantic Schema。
- 定义首版组件 validation profiles；profile 只进入临时 artifact，不成为组件字段。
- 从现有 `CodeCheckService.check_component_code` 抽取/封装统一组件校验编排入口。
- AI 新建组件在写入前执行 contract + compile。
- AI 修改源码继续自动 check，并改用统一结果契约。
- AI 修改 `previewSchema` 在写入前执行 contract + compile。
- 三类工具统一 `success/applied/validation` 返回语义。
- 将 `validate_entity(component.check)` 迁移到同一结果契约，支持 current、候选源码/edits、候选 schema 和临时新组件检查。
- 更新 `tool_specs.py` 及防漂移测试，明确独立 check 可按需调用、三类写工具会自动 check，无需重复预检。

阶段一完成后，三类操作至少都能向模型反馈候选是否可编译，但尚不能声称实际渲染正常。

### 阶段二：真实渲染与布局反馈（基础版已完成）

目标是回答“实际结果有没有问题”。

- 新增 `ComponentRenderDiagnosticsService` 并接入共享 Playwright 池。
- 补充或版本化 Runtime 组件预览协议，提供可靠 `render-settled` 信号。
- 执行 default 和有界 presets，捕获启动错误、运行时错误和资源失败。
- 返回根节点、frame、overflow、clip 和尺寸响应等布局事实。
- 按页面/内容/原子组件实施不同规则。
- scenario 与 diagnostic 返回实际 `profile_key`，明确布局结论的环境边界。
- 将三类 AI 写操作统一升级为 contract + compile + render。
- warnings 随成功写入反馈给模型，确定性 render/layout error 阻止写入。

### 阶段三：稳定性与成本治理（待实施）

- 对相同 candidate hash 和同一 Runtime/规则版本增加短期结果缓存。
- 校验缓存 key 同时包含 validation profile 版本、主题 fingerprint 和 Runtime 版本，环境变化时不得复用旧结果。
- 补充诊断超时、队列容量、场景上限和日志截断指标。
- 区分候选错误与基础设施 unavailable，支持智能体安全重试。
- 根据真实耗时决定是否需要异步 check；首期不直接复用页面 mutation job 状态机。
- 用真实案例调校布局阈值，低置信度规则保持 warning。

## 10. 测试计划

### 10.1 Backend unit/contract

- 新建组件、修改源码、修改 schema 都在写入前调用统一校验服务。
- 任一阶段 failed 时 `applied=false`，数据库不发生变化。
- unavailable 时不写入，结果为 `retryable=true`。
- passed_with_warnings 时允许写入并完整返回 warnings。
- edits 的 canonical diff 与实际写入内容一致。
- 检查后候选基线发生变化时拒绝写入，避免 TOCTOU。
- 临时组件、传递依赖、Runtime Kit 边界和循环依赖行为保持正确。
- 三类工具规格、运行时注册、返回示例和自动校验说明一致。
- `validate_entity(component.check)` 与三类写工具对相同候选产生一致的阶段状态、诊断码和 candidate hash。
- 独立 check 不产生组件写入，临时 artifact 始终清理。

### 10.2 Runtime 与渲染诊断

- compile failed 时不占用浏览器池。
- `ready/error/render-settled` 在 default 和 preset 切换中稳定。
- setup/render 异常、动态依赖失败和关键资源失败映射到稳定 code。
- 空白、零尺寸、完全越界、水平/垂直溢出和裁切规则可重复。
- 页面、内容、原子组件使用各自布局规则。
- 组件 check 不读取当前焦点项目尺寸和基础字号，固定 profile 下结果可重复。
- profile 的页面尺寸和基础字号只进入 artifact，不进入组件、版本或 `previewSchema`。
- scenario 结果携带 profile key；profile 或主题 fingerprint 变化时缓存失效。
- 场景去重、数量上限和超限 warning 正确。
- 超时或池不可用映射为 unavailable，不映射为候选源码错误。
- 无论通过、失败或取消，Playwright page 和 artifact 都被回收。

### 10.3 AI 工具闭环

- 新建组件第一次编译失败，模型收到诊断后修复并成功创建。
- 源码可编译但默认态 render 抛错时不保存 edits。
- 修改 schema 后某个 preset 报错时不保存 schema。
- 布局 warning 随成功结果返回，模型可继续优化但不会误判为未写入。
- 基础设施 unavailable 时模型不会无依据改写候选。

建议实施时按改动范围运行 Backend unit/integration、根仓 contracts、Runtime delegated tests，并为三类工具各补一个跨 Backend/Runtime 的集成场景。只有涉及真实浏览器链路时再增加对应 E2E regression。

## 11. 风险与约束

- 浏览器 check 成本高于 compile，必须复用共享池、限制场景数并设置分阶段超时。
- 布局是启发式判断。除空白、零尺寸和完全越界外，首期应以 warning 为主。
- preset 可能包含异步 mock。协议需要明确“渲染稳定”的判定，不能只等网络空闲或固定时长。
- console 中可能混入 Runtime 噪声。只有能够归因到候选组件的 error 才应阻断。
- 诊断中可能包含源码片段和本机路径。返回模型前需要脱敏、去重和截断。
- check 与写入之间存在并发窗口。三类操作都要复核候选基线，不能只依赖组件 ID。
- 单一 profile 只能证明候选在该环境下的结果。具体项目中的兼容性仍由带真实页面配置的页面 check 负责。
- 自动 check 是模型反馈能力，不等于证明组件业务语义完全正确；用户仍通过预览判断视觉和内容是否符合预期。

## 12. 推荐最终边界

- AI 写工具对新建组件、源码修改和 `previewSchema` 修改承担自动 check 责任。
- `validate_entity(component.check)` 提供与页面 check 对齐的只读独立调用能力。
- Backend 统一组装候选、执行三层校验、决定是否写入并返回结构化结果。
- Runtime 负责完整 artifact 的编译与组件预览执行，并提供可稳定等待的运行信号。
- Playwright 诊断负责收集真实运行错误和高置信度布局事实，不判断业务审美。
- 模型直接消费写工具返回的 validation 短文本形成修复闭环；需要受控明细时调用 `validate_entity(detail=true)`，无需重复执行无诊断目的的独立检查。
- Editor 继续承担用户预览和报错呈现，不新增本方案专用的 check 交互。

最终闭环应是：模型提交完整候选，系统在不污染已有组件的前提下真实编译和渲染，失败时返回可定位、可修复的事实，通过后再写入，并把非阻断布局问题继续反馈给模型。
