<!-- 文件用途：说明工作空间组件如何在后台以独立 JSON 配置的方式管理 previewSchema。 -->
# 组件预览 `previewSchema` 指南

本文档面向“工作空间共享组件”的作者，说明如何在后台为组件维护独立的 `previewSchema` JSON，从而让组件预览支持：

- `props` 面板
- `slots` 面板
- `mock` 静态状态配置
- `presets` 预设切换

当前组件预览运行在 Runtime 的纯沙箱宿主页中，正式组件源码仍通过发布产物远程模块方式加载。

## 1. 基本约定

`previewSchema` 不再从组件源码里读取，而是由 Backend 单独保存并随组件预览配置一起下发。

推荐在组件管理后台的独立 `previewSchema (.json)` 编辑器中维护，例如：

```json
{
  "props": {},
  "slots": {},
  "mocks": {},
  "presets": []
}
```

注意：

- `previewSchema` 必须是合法 JSON 对象。
- 不支持函数、表达式或任意可执行代码。
- 没有配置 `previewSchema` 的组件仍然可以被预览，但后台不会显示调参面板。

## 2. `props` 字段

当前支持的字段类型：

- `string`
- `textarea`
- `number`
- `boolean`
- `select`
- `json`

示例：

```ts
{
  props: {
    title: {
      type: 'string',
      label: '标题',
      default: '季度经营看板',
    },
    collapsed: {
      type: 'boolean',
      label: '默认收起',
      default: false,
    },
    tone: {
      type: 'select',
      label: '视觉风格',
      default: 'primary',
      options: [
        { label: '主色', value: 'primary' },
        { label: '成功', value: 'success' },
        { label: '警示', value: 'warning' },
      ],
    },
    metrics: {
      type: 'json',
      label: '指标列表',
      default: [
        { label: '订单量', value: 1280 },
        { label: '支付率', value: 0.73 },
      ],
    },
  },
}
```

建议：

- `string`、`textarea` 用于普通文案。
- `number` 只用于真正的数值输入，不要混用字符串数字。
- `json` 适合复杂对象、数组、配置项集合。
- `select` 的 `default` 值应与 `options[].value` 精确匹配。

## 3. `slots` 字段

当前 `slots` 采用**声明式节点**描述，不支持任意模板字符串或 JS 渲染函数。

支持的节点类型：

- `text`
- `html`
- `component`

### 3.1 `text`

```ts
slots: {
  default: {
    label: '默认插槽',
    default: [
      { type: 'text', value: '这里是一段默认插槽文案。' },
    ],
  },
}
```

### 3.2 `html`

```ts
slots: {
  footer: {
    label: '底部说明',
    default: [
      { type: 'html', value: '<strong>数据更新时间：</strong> 09:30' },
    ],
  },
}
```

说明：

- `html` 适合少量受控富文本。
- 请只写可信内容，不要把不受控用户输入直接拼进去。

### 3.3 `component`

```ts
slots: {
  actions: {
    label: '操作区',
    default: [
      {
        type: 'component',
        component: '@runtime-kit/public/components/primitives/Icon.v1.vue',
        props: {
          name: 'star',
          size: 18,
        },
      },
    ],
  },
}
```

`component` 节点当前只允许引用：

- Runtime Kit 公开清单中的版本化基础能力：`@runtime-kit/...`
- 工作空间组件：`@workspace-components/<component_code>/v/<version_no>`

不允许引用：

- `@/views/...`
- `@/components`、`@/layouts`、`@/core`、`@/styles` 等 Runtime 私有路径
- Runtime Kit manifest 未声明的模块
- 任意动态 `import()`

## 4. `mock` 静态状态

`mocks` 是 component-preview 宿主页内部的静态状态，不通过 `@runtime-kit` 向页面源码、工作空间组件源码或智能体公开。普通组件应优先通过 `props` 和 `slots` 接收可调数据。

面板中的 `mocks` 当前仅支持 JSON/文本级静态值，不支持：

- 函数
- 表达式
- HTTP 请求 mock

示例：

```ts
{
  mocks: {
    stats: {
      label: '统计数据',
      default: [
        { label: '新增客户', value: 12, trend: '+18%' },
        { label: '续费率', value: '84%', trend: '+6%' },
      ],
    },
  },
}
```

## 5. `presets` 预设

`presets` 用于快速切换一组完整的 `props / slots / mocks`。

示例：

```ts
{
  presets: [
    {
      key: 'compact',
      label: '紧凑版',
      props: {
        title: '紧凑看板',
        collapsed: true,
      },
    },
    {
      key: 'highlight',
      label: '强调版',
      props: {
        tone: 'warning',
      },
      mocks: {
        stats: [
          { label: '异常数', value: 23, trend: '+12%' },
        ],
      },
    },
  ],
}
```

建议：

- `key` 保持稳定，不要使用会频繁变化的值。
- `label` 直接面向后台使用者展示，尽量简短清晰。
- 预设只写覆盖值，未声明的字段会回退到 schema 默认值。

## 6. 完整示例

仓库内提供了一个完整示例组件实现，可直接参考：

- [PreviewSchemaDemoCard.vue](/C:/code/web-presentation/runtime/src/examples/public/component-preview/PreviewSchemaDemoCard.vue)

它演示了组件在预览场景中的这些能力：

- `props` 的多种字段类型
- `slots` 的 `text / html / component`
- `mocks` 静态状态
- `presets` 预设

## 7. 推荐实践

- 保持 `previewSchema` 和组件真实 API 一致，不要为了预览单独发明一套 props 名称。
- `mocks` 更适合承载列表、统计卡片、图表数据等大块结构化数据。
- 对插槽优先提供可读的默认值，方便第一次打开时立即看到效果。
- 如果一个组件非常复杂，优先先给出 2 到 3 个高质量 `presets`，再补细粒度字段。
- 不要在组件源码中导入 component-preview 专用的 Runtime 内部能力；需要可调数据时优先建模为 `props` 或 `slots`。

## 8. 当前限制

当前版本暂不支持：

- 自动从 `defineProps` 推导表单
- 任意 JS 表达式 / render 函数
- 动态 `import()`
- 通过网络请求拉取 mock 数据
- 在后台直接编辑或组合 slot 子组件树的可视化拖拽
