# 富文本源码范围定位加固计划

本文档记录页面可视化编辑分析器对富文本容器源码范围定位的修复计划。计划聚焦 Runtime 的 Vue SFC 静态分析，不改变 Backend 作为页面源码唯一事实源的边界，也不扩大当前受限富文本的写入能力。

## 1. 背景

页面可视化编辑会把 `p`、`span`、标题、`li`、`blockquote`、`label` 等文本容器分析为 `rich_text` binding，并把 binding 的 `sourceRange` 限定在容器 opening tag 与 closing tag 之间。

当页面包含以下装饰性自闭合节点时：

```vue
<span class="block size-3 rounded-full bg-accent6-600" />
<span
  v-for="n in 6"
  :key="n"
  class="block h-2.5 rounded-full"
  :class="n <= 3 ? 'w-8 bg-primary' : 'w-2.5 bg-primary/20'"
/>
```

分析过程会抛出：

```text
无法定位富文本容器 <span> 的内部源码范围。
```

异常会中断整份页面 Manifest 的生成，使页面无法进入可视化编辑，而不是只将问题节点降级为只读。

## 2. 已确认根因

当前调用链为：

```text
analyzeElementNode
  -> isRichTextContainer
  -> classifyRichTextContent
  -> buildRichTextBinding
  -> resolveElementInnerRange
  -> resolveElementShell
```

问题由两个条件共同触发：

1. `span` 位于富文本容器标签集合中，空的自闭合 `span` 会被分类为静态富文本。
2. `resolveElementShell()` 对无子节点且没有 closing tag 的元素返回 `{ openingTag, closingTag: '' }`，表示该元素没有内部内容；`resolveElementInnerRange()` 随后使用 `if (!shell?.closingTag)` 判断，空字符串被 JavaScript 当作假值，最终误判为定位失败。

现有实现混淆了三种状态：

| 状态 | 含义 | 期望处理 |
| :--- | :--- | :--- |
| `shell === null` | opening/closing shell 无法可靠解析 | 不生成可写富文本 binding，并输出诊断 |
| `closingTag === ''` 且源码为自闭合元素 | 节点没有可编辑内部内容 | 作为普通空节点处理，不生成富文本 binding |
| `closingTag !== ''` | 有明确 opening/closing tag | 生成内部内容源码范围 |

因此，单纯把异常条件改成 `if (!shell)` 虽能消除抛错，但会把自闭合元素的插入点错误地解释为可编辑富文本范围，允许后续把 `<span />` 改写成语义不完整的源码。修复需要同时调整分类和范围解析职责。

## 3. 修复目标

- 自闭合 `span` 等非 void 元素不再触发整页分析异常。
- 自闭合装饰节点不生成 `rich_text` binding，也不开放文本插入能力。
- 成对空容器 `<span></span>` 继续生成 `start === end` 的可编辑富文本插入范围。
- 普通静态富文本、锁定标签富文本和动态混排的既有行为保持不变。
- 带 `v-for`、`v-if` 等结构指令的节点继续按结构语义分析，不因富文本兜底丢失节点或循环定位信息。
- 单个节点无法定位内部源码范围时，分析器降级并返回结构化诊断，不中断整个页面 Manifest。
- 不改变可视化编辑协议版本、Backend API 或 Editor 提交结构。

## 4. 非目标

- 不开放自闭合 HTML 非 void 标签的文本编辑。
- 不扩大富文本允许的标签、属性或 Vue 表达式范围。
- 不处理浏览器对非法 HTML 的运行时纠错结果；源码分析仍以 Vue SFC 编译器 AST 为准。
- 不在本次工作中调整 Editor 富文本编辑器交互。
- 不为无法静态定位的节点猜测源码 offset。

## 5. 实施步骤

### 5.1 先建立失败用例

在 Runtime 的 SFC 分析测试中加入完整或最小化回归 fixture，至少覆盖：

```vue
<template>
  <main>
    <span class="dot" />
    <span v-for="n in 6" :key="n" class="indicator" />
    <span></span>
    <span>正文</span>
  </main>
</template>
```

测试先证明当前实现对第一个自闭合 `span` 抛错，再用于验证修复后行为。测试应直接调用 `analyzeVisualEditSfc()`，避免只测试内部辅助函数而遗漏模板遍历与 Manifest 生成链路。

### 5.2 明确元素 shell 类型

调整 `rich-text.ts` 中的 shell 解析结果，避免继续使用空字符串隐式表达自闭合状态。推荐使用可判别联合：

```ts
type VisualEditElementShell =
  | {
      kind: 'paired'
      openingTag: string
      closingTag: string
    }
  | {
      kind: 'self-closing'
      openingTag: string
    }
```

解析失败继续返回 `null`。调用方必须显式处理 `paired`、`self-closing` 和 `null`，不再依赖字符串真假值判断。

识别自闭合元素时，应根据原始 `element.loc.source` 的 opening tag 结尾判断 `/>`，不能仅以“没有子节点”推断；成对空容器同样没有子节点，但需要保留零长度插入范围。

### 5.3 在分类阶段排除自闭合富文本

富文本容器判定除标签类型外，还应确认节点具有成对标签。建议把判断拆成两个职责：

- `isRichTextContainerTag()`：只判断标签是否属于富文本候选集合。
- `resolveRichTextContainerKind()`：结合 shell、结构指令和子节点判定是否进入富文本分析。

自闭合富文本候选应返回“不聚合”，随后按普通元素节点进入 prop、循环和子节点分析。这样可以保留节点 marker、Tailwind class binding 和 `v-for` 上下文，同时不创建不存在的内部文本 binding。

### 5.4 让范围解析返回可处理结果

`resolveElementInnerRange()` 不应对页面源码形态直接抛出通用异常。建议改为返回：

```ts
VisualEditSourceRange | null
```

只有 `paired` shell 才返回内部范围：

```text
start = element.loc.start.offset + openingTag.length
end   = element.loc.end.offset - closingTag.length
```

`self-closing` 和解析失败返回 `null`，由分析层决定跳过 binding 或生成只读诊断。范围函数仍应校验 `start <= end` 且范围落在元素 `loc` 内，防止错误 offset 进入 Manifest。

### 5.5 增加节点级降级与诊断

即使分类与 shell 解析以后出现漂移，单个富文本节点也不应中断整页分析。`buildRichTextBinding()` 应改为可返回 `null` 或结构化结果：

```ts
{
  binding: VisualEditBinding | null
  diagnostic?: VisualEditDiagnostic
}
```

无法定位时：

- 保留该模板节点及其普通 prop binding。
- 不生成可写 `template-rich-text` source。
- 尽可能继续遍历子元素。
- 在 Manifest diagnostics 中记录稳定错误码，例如 `RICH_TEXT_SOURCE_RANGE_UNRESOLVED`。
- diagnostic 的 `sourceRange` 指向整个元素范围，而不是伪造内部范围。

该诊断属于页面级只读降级，不应让 Runtime 分析接口返回 500。

### 5.6 检查写回边界

确认 `set_rich_text` 仍只接受同时满足以下条件的 binding：

- `kind === 'rich_text'`
- `editable === true`
- `source.kind === 'template-rich-text'`
- `sourceRange` 来自成对容器的内部范围

自闭合节点不应出现在可写目标集合中。现有 apply 阶段的 baseline hash、binding ID 和锁定标签骨架复核保持不变。

## 6. 测试矩阵

### Runtime 单元测试

| 场景 | 预期 |
| :--- | :--- |
| `<span />` | 分析成功，无 `rich_text` binding |
| `<span class="dot" />` | 保留节点及静态 class binding，无富文本 binding |
| `<span v-for="n in 6" :key="n" />` | 保留循环节点和循环上下文，不抛错 |
| `<span></span>` | 生成可编辑富文本 binding，`start === end` |
| `<span>正文</span>` | 生成可编辑富文本 binding，范围只覆盖“正文” |
| `<p>普通 <strong>重点</strong></p>` | 保持现有结构化富文本行为 |
| `<p>{{ value }}</p>` | 保持单一插值 text binding 行为 |
| `<p>前缀 {{ value }}</p>` | 保持动态混排只读行为 |
| shell 无法解析的异常 fixture | 整页分析成功，节点降级并产生诊断 |

### Runtime 写回测试

- 验证自闭合节点不存在可用于 `set_rich_text` 的 binding。
- 验证成对空容器仍可通过零长度范围插入富文本。
- 验证伪造自闭合节点 binding 或源码范围时，apply 阶段明确拒绝。
- 验证普通富文本替换、锁定标签移除和结构校验不回归。

### 根仓契约测试

- 若只新增 diagnostic code 且协议字段结构不变，不升级协议版本。
- 更新防漂移测试，确认 Runtime 输出仍能通过 Backend Manifest schema 校验。
- 验证 Runtime 分析失败不会被错误映射成可重试的基础设施异常。

### 建议执行命令

```powershell
pnpm --dir runtime test -- src/core/visual-edit/source/analyze-sfc.test.ts
pnpm --dir runtime test -- src/core/visual-edit/apply/apply-operations.test.ts
pnpm run test:runtime
pnpm run test:contracts
```

如改动触及 Backend 对 Runtime 错误或诊断的映射，再补充：

```powershell
pnpm run test:backend:unit
```

## 7. 验收标准

- 已知包含多个自闭合装饰性 `span` 的页面能够生成可视化编辑 Manifest。
- Manifest 中成对空 `span` 与自闭合 `span` 的语义不同：前者有零长度富文本 binding，后者没有富文本 binding。
- 自闭合循环 `span` 的节点、循环定位和可编辑 class 能力不丢失。
- 任一单节点 shell 定位失败不会导致整页分析接口失败。
- 新增测试覆盖分析、写回和契约边界，现有富文本测试全部通过。
- Runtime 独立项目文档同步说明自闭合文本候选节点的处理规则。

## 8. 交付拆分

建议按以下顺序提交，便于评审和回滚：

1. 增加失败 fixture 和回归测试，不调整协议。
2. 重构 shell 判别类型与富文本容器分类。
3. 增加节点级降级诊断并补齐写回防御测试。
4. 更新 Runtime 独立文档和根仓契约说明。

如果实施中确认无需新增 Manifest diagnostic 字段，只增加既有 `diagnostics` 数组中的错误码，则以上工作可以在协议版本 `1` 内完成。
