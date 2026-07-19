# 页面可视化编辑契约

页面可视化编辑是在现有 Vue SFC 页面源码和 Runtime preview artifact 之上的受限编辑能力。它不引入第二份页面 DSL，也不改变 Backend 作为页面源码和版本唯一事实源的边界。

## 1. MVP 边界

首期支持：

- 静态模板文本、静态组件参数和静态 Tailwind 类。
- `p`、`span`、标题、`li`、`blockquote`、`label` 内的结构化富文本；静态文本可编辑，链接、组件和属性等标签外壳锁定。
- `const`、`ref`、`reactive` 包装的数组字面量。
- 带稳定基本类型 `key` 的单层 `v-for`。
- `item.title`、`:prop="item.value"`、`:class="item.className"` 这类可静态追溯绑定。
- 基于 artifact 实际组件版本 `previewSchema` 的字符串、数字、布尔和枚举控件。
- 与节点直接关联的顶层 `const`、`ref`、`reactive` 纯 JSON 数组或对象整块编辑，以及 `previewSchema.type=json` 的组件参数。
- 普通结构、段落和组件的模板节点复制、删除。
- 稳定单层 `v-for` 数据项的复制、删除，以及整个循环模板的删除。

首期不支持：

- 保存前实时更新 Runtime 画布。
- 元素新增、拖拽、排序、整个 `v-for` 模板复制和嵌套 `v-for` 编辑。
- `computed`、`map`、异步请求、导入数据、函数调用、条件表达式和字符串拼接的反向写入。
- JSON 中的 spread、函数、调用、变量值、计算属性、模板插值、`undefined`、BigInt 和重复对象键。
- `<style>`、内联复杂 CSS、Tailwind 任意值、动态构造类名以及组件内部 DOM 编辑。

不能静态证明唯一写入位置的内容必须以只读状态披露原因，不允许根据渲染结果猜测源码位置。

## 2. 模块职责

### Backend

- 读取规范 `PageVersion` 源码并校验用户、工作空间和项目权限。
- 创建带编辑 Manifest 和插桩页面模块的短期 preview artifact。
- 校验 artifact、页面版本、源码 hash 和批量编辑操作。
- 调用 Runtime 的纯源码分析/改写能力，完成代码检查后原子创建新页面版本。
- 插桩源码只允许进入短期 artifact，不得写入页面或页面版本表。

### Runtime

- 使用与 Vue Runtime 同版本的 SFC 编译器分析 Backend 下发源码。
- 生成模板语义树、绑定信息、只读原因和预览态插桩源码。
- 在编辑态 iframe 中上报节点选择、组件实例范围和 `v-for` 实例路径。
- 根据 Backend 提供的规范源码和结构化操作返回改写后的完整源码。
- 不访问平台数据库，不保存页面版本，不接受 Editor 直接写入源码。

### Editor

- 展示源码语义图层树、Runtime 画布和受限属性面板。
- 在本地合并待提交操作；保存前不向 Runtime 发送属性覆盖。
- 通过 Backend 批量保存，成功后重新创建 artifact 并刷新 iframe。
- 不提交源码 offset、任意 AST 路径或自行拼装的完整页面源码。

## 3. 协议版本

当前首发协议版本固定为整数 `1`。协议尚未发布，不保留历史版本兼容分支；Backend、Runtime 和 Editor 必须拒绝未知版本，并通过根仓契约测试防止字段漂移。

编辑节点使用 `node_id`，可编辑绑定使用 `binding_id`。两者只要求在同一规范源码 hash 内稳定；页面保存后必须重新分析，不能把旧 ID 自动重放到新版本。

## 4. 编辑态 artifact

创建接口：

```http
POST /pages/{page_id}/visual-edit/preview-artifacts
```

请求至少包含：

```json
{
  "protocol_version": 1,
  "base_version_no": 12
}
```

响应在标准预览响应之外增加：

```json
{
  "visual_edit": {
    "protocol_version": 1,
    "page_id": 123,
    "base_version_no": 12,
    "source_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "manifest": {},
    "component_schemas": {},
    "warnings": []
  }
}
```

artifact manifest 使用 `page_visual_edit_preview` 类型，并绑定用户/租户、工作空间、项目、页面、页面版本、源码 hash、逻辑模块路径和协议版本。MVP 使用现有 artifact TTL，不新增持久化编辑会话表。

Manifest 每个节点通过 `template_actions` 声明模板级 `can_duplicate`、`can_delete` 和只读原因；处于可编辑循环中的节点另通过 `loop_item_actions` 声明循环项级能力、`loop_node_id`、数据源与稳定 `{ key, index }` 实例列表。Editor 只能展示 Manifest 已开放的操作，Backend 保存时必须再次复核这些能力和实例身份。

`component_schemas` 以页面源码中的默认导入本地名为 key。工作空间组件只允许从 `@workspace-components/<code>/v/<version>` 的精确钉住版本读取 `previewSchema.props`，不得回退组件当前草稿或最新版本；Runtime Kit 组件从其版本化能力清单读取。公开元数据仅保留属性控件需要的类型、标签、说明、默认值和有限选项，不下发 slots、mocks 或 presets。

## 5. 批量保存

保存接口：

```http
POST /pages/{page_id}/visual-edit/apply
```

请求示例：

```json
{
  "protocol_version": 1,
  "artifact_id": "rt_xxx",
  "base_version_no": 12,
  "source_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "operations": [
    {
      "type": "set_value",
      "node_id": "node_title",
      "binding_id": "binding_text",
      "instance_path": [
        {
          "loop_node_id": "for_items",
          "key": "b",
          "index": 1
        }
      ],
      "value": "新标题"
    },
    {
      "type": "set_json",
      "source_id": "source_benefits",
      "value": ["上下文稳定", "品牌统一", "交付更快"]
    },
    {
      "type": "set_rich_text",
      "node_id": "node_summary",
      "binding_id": "binding_summary_rich",
      "instance_path": [],
      "html": "第一行<br><strong>重点</strong><em>补充</em>"
    },
    {
      "type": "duplicate_node",
      "node_id": "node_card",
      "instance_path": [
        { "loop_node_id": "for_items", "key": "b", "index": 1 }
      ]
    },
    {
      "type": "delete_node",
      "node_id": "node_section",
      "instance_path": []
    }
  ],
  "change_note": "可视化编辑"
}
```

同一批操作必须全部成功或全部失败。保存成功只负责返回新页面版本；Editor 随后重新调用编辑态 artifact 接口。这样可以区分“源码已保存但预览生成失败”和“源码未保存”。

## 6. `v-for` 定位规则

Runtime 选择消息应携带由外到内的 `instance_path`。单层 MVP 中必须优先用稳定 `key` 匹配数组对象，`index` 只用于辅助验证。

结构操作按 `instance_path` 区分作用域：普通节点空路径表示模板节点；循环内节点携带实例路径时表示对应数组项；直接带 `v-for` 的节点空路径只允许删除整个循环模板，不允许复制。复制数组项时字符串 key 使用 `-copy` 后缀避重，整数 key 使用未占用的安全整数；删除唯一项后允许保留空数组。

以下情况首期只读：

- 缺少 `key`、重复 key 或 key 不是字符串/整数。
- 数据源不是本地数组字面量或 `ref`/`reactive` 包装的数组字面量。
- 绑定值经过函数、计算属性、条件或字符串拼接。
- 无法把循环别名唯一解析到数据源对象属性。

## 7. Tailwind 约束

可视化选项必须从 Runtime safelist 派生的版本化目录下发，Editor 不维护第二份类清单。服务端按冲突组替换目标工具类，未识别类、响应式前缀、状态类和任意值应原样保留并只读展示。

Manifest v1 中的 Tailwind 目录使用独立版本 1 的以下结构；`label` 是面向用户的可视说明，Editor 不提供任意 class 文本框：

```json
{
  "tailwind_catalog": {
    "version": 1,
    "groups": [
      {
        "key": "padding",
        "label": "内边距",
        "options": [
          { "class_name": "p-4", "label": "中等（16px）" }
        ]
      }
    ]
  }
}
```

动态构造类名，例如 ``bg-${color}-500``，不允许进入可视化编辑操作。

`style`、`:style` 和 SFC `<style>` 块均不生成可编辑 binding；样式写回只允许走上述 Tailwind 目录。

### 整块 JSON 约束

- Runtime 在 Manifest 的 `json_sources` 中按 `source_id` 去重静态 JSON 字面量，节点 binding 只引用 source，不向 Editor 授权源码 offset。
- 顶层脚本 source 只接受数组或对象，并在保存时保持原有根类型；组件内联 JSON 参数接受标准 JSON 值。
- `set_json` 只提交结构化 JSON，Runtime 重新定位规范源码并确定性序列化，不能提交原始 JavaScript 或完整页面源码。
- 单值上限为 UTF-8 200000 字节、32 层和 10000 个节点；Editor、Backend、Runtime 均执行同样校验。
- 同批次整块 JSON 与其内部字段、样式或结构操作互斥。组件 JSON 参数首期只校验通用 JSON，不提供 JSON Schema 语义保证。
- 基本类型数组通过循环节点的数据编辑器整块修改，不开放逐项 index 写回、复制或删除；编辑期间画布仍保持当前 artifact，保存后刷新。

## 8. Runtime 选择消息

编辑态 iframe 上报画布点击选择，同时接收 Editor 图层树的节点定位；它仍不接收草稿样式、文本或参数覆盖。双方都必须校验 `event.source`、origin、artifact、协议版本以及 Manifest 中是否存在目标节点：

```json
{
  "type": "page-visual-edit:selection",
  "payload": {
    "protocolVersion": 1,
    "artifactId": "rt_xxx",
    "nodeId": "node_card",
    "instancePath": [
      {
        "loopNodeId": "node_items",
        "key": "b",
        "index": 1
      }
    ]
  }
}
```

Editor 主动定位使用同一 payload 字段，并将事件类型改为 `page-visual-edit:select-node`。空 `instancePath` 表示模板级选择，循环节点会高亮全部实例；带稳定 key 时只定位对应实例。`Page` 或 `template` 等无直接 DOM 的逻辑节点由 Runtime 高亮其最近可渲染后代。

## 9. 受限富文本

- 可编辑 binding 使用 `kind: rich_text` 与 `source.kind: template-rich-text`，源码范围只覆盖容器 opening/closing tag 之间的内容。
- `set_rich_text.html` 允许转义文本、`br`、用户可增删的 classless `strong/em`，以及从规范源码原样保留的锁定标签外壳。链接、组件、静态或动态属性、内联 style 和其他标签均作为锁定外壳处理，Backend 负责基础语法、Vue 文本插值和 20000 字符限制，Runtime 结合当前源码执行最终结构校验。
- Editor 递归拆分普通文本、可变语义标签与锁定标签；锁定标签内外的静态文本都可编辑，用户只能在单个文本片段内选择非空文本添加 classless `strong/em`，换行统一序列化为 `br`。
- 锁定标签只显示“样式锁定”，用户点击后才展示原始 opening tag 与属性；点击“删除锁定样式”只移除标签外壳，内部文本和子标签提升到父级并与相邻文本合并。classless `strong/em` 取消标签时遵循相同的内容保留与合并规则。
- Runtime 应以规范源码为基准复核锁定标签骨架。候选可移除任意锁定外壳并提升其后代，但不能新增或修改链接属性、组件参数、动态属性、style、class，也不能重排或错误重新挂载剩余节点；违反时返回 `422 PAGE_VISUAL_EDIT_RICH_TEXT_STYLE_LOCKED`。
- 单一动态插值继续使用原有 `text` binding；静态文本与表达式混排时生成整段只读富文本，避免拆层或破坏动态源码。
- Editor 只在本地维护富文本草稿，保存成功并重新生成 artifact 后画布才显示新内容。

## 10. 并发与失败语义

- Backend 保存前后都要复核 `base_version_no` 和 `source_hash`。
- 两个请求基于同一版本时只允许一个创建下一版本，另一个返回 `409`。
- artifact 过期、归属错误、协议不兼容、Runtime 超时、AST 歧义或代码检查失败时不得创建页面版本。
- 一旦页面被 Monaco、AI Agent、版本恢复或其他窗口更新，旧编辑会话必须失效，不能自动重放旧节点 ID。
- 保存成功、artifact 刷新失败时不得重复提交已落库操作，只允许重新生成预览。

## 11. 首期验收场景

基准页面必须包含 `const items = [...]`、稳定 `:key="item.id"`、文本绑定、组件参数和 Tailwind class 绑定。验收时选择第二个循环实例，同时修改文本、组件参数和间距，保存前画布保持不变；保存后只创建一个页面版本，且只有对应 key 的数组项发生变化。

同时验证动态表达式只读、未知 Tailwind 类保留、跨工作空间拒绝、并发冲突不覆盖、任一非法操作导致整批不落库。
