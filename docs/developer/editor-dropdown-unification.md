# Editor 下拉框统一治理：调研结果与实施计划

## 1. 调研结果

### 1.1 下拉组件全景

Editor 中共存在 **6 种下拉实现** + 1 处原生 `<select>`，分布在 UI 组件库和业务组件两个层面。

#### UI 组件库（4 个）

| 组件 | 文件 | 底层 | 浮层 z-index（改前） | 使用次数 | 状态 |
|---|---|---|---|---|---|
| UiSelect | `ui/select/UiSelect.vue` | Reka SelectRoot + SelectPortal | z-[900] | 24 处 | 正常 |
| SearchableSelect | `ui/SearchableSelect.vue` | 手写，Teleport to body | z-[1600] | 20 处 | 正常 |
| UiCombobox | `ui/select/UiCombobox.vue` | Reka ComboboxRoot | z-[900] | **0 处** | 死代码 |
| UiDropdownMenu | `ui/menu/UiDropdownMenu.vue` | Reka DropdownMenuRoot | z-[900] | **0 处** | 死代码 |

#### 业务组件手写下拉（6 处）

| 组件 | 文件 | 定位方式 | z-index | click-outside |
|---|---|---|---|---|
| UserMenu | `nav/UserMenu.vue` | absolute | z-50 | 内联指令（第 1 份） |
| WorkspaceSwitcher | `nav/WorkspaceSwitcher.vue` | absolute | z-50 | 内联指令（第 2 份） |
| ProjectQuickSwitcher | `nav/ProjectQuickSwitcher.vue` | absolute | z-50 | 内联指令（第 3 份） |
| AgentSessionControls | `agent/AgentSessionControls.vue` | absolute | z-30 | 内联指令（第 4 份） |
| PreviewSizePresetSelect | `preview-size/PreviewSizePresetSelect.vue` | Teleport to body | z-[1700] | 手动 mousedown 监听 |
| PlacementToolbar（inline 模式） | `component-preview/ComponentPreviewPlacementToolbar.vue` | Teleport to body | z-[1800] | 手动 mousedown 监听 |

另外 `AgentConversationPanel.vue` 的模型选择菜单也是手写 absolute 浮层（z-30），无 Teleport，存在被父容器 overflow 裁切的风险。

#### 原生 `<select>`

`ui/PaginationControl.vue` 的"每页条数"选择器，是 editor 中唯一一处原生 select。功能正常但视觉风格不统一。

### 1.2 SearchableSelect 调用明细（20 处）

所有调用均为**单选**，未使用 `multiple`。使用的 props 汇总：

| Props | 使用次数 | 说明 |
|---|---|---|
| `placeholder` | 20 | 全部使用 |
| `clearable` | 8 | ThemeEditorDialog ×5、WorkspaceStyleApplyField、ThemeSelectorField、AccountAiSettingsView ×2 |
| `search-placeholder` | 6 | ComponentEditorPane、WorkspaceStyleApplyField、ThemeEditorDialog ×3、ThemeSelectorField |
| `empty-text` | 6 | ComponentEditorPane、PageBatchCopyToProjectDialog ×2、PageCopyToProjectDialog ×2、ProjectRouteTreeTable ×4 |
| `size="compact"` | 4 | ProjectRouteTreeTable ×3、AccountAiSettingsView ×2 |
| `disabled` | 5 | AccountAiProviderDetail、PageBatchCopyToProjectDialog ×2、PageCopyToProjectDialog ×2、WorkspaceStyleApplyField、ThemeSelectorField |
| `multiple` | **0** | 无调用方使用多选 |

调用方分布：

- `AccountAiModelDetail.vue` ×1（供应商配置选择）
- `AccountAiProviderDetail.vue` ×1（供应商选择）
- `ComponentEditorPane.vue` ×1（组件类型选择）
- `PageBatchCopyToProjectDialog.vue` ×2（目标项目、目标分组）
- `PageCopyToProjectDialog.vue` ×2（目标项目、目标分组）
- `ProjectRouteTreeTable.vue` ×4（顶层页面、子页面、分组页面选择）
- `WorkspaceStyleApplyField.vue` ×1（工作空间样式选择）
- `ThemeEditorDialog.vue` ×5（Logo、反色 Logo、标题/正文/代码字体）
- `ThemeSelectorField.vue` ×1（主题选择）
- `AccountAiSettingsView.vue` ×2（模型槽位选择）

### 1.3 测试依赖

- `SearchableSelect.test.ts`：3 个用例（搜索过滤单选、多选数组输出、向上展开定位）
- `ComponentEditorPane.test.ts`：2 处 stub（`SearchableSelect: true`）
- `ThemeEditorDialog.test.ts`：1 处 stub（defineComponent mock）
- E2E（Playwright）：**无**直接依赖 SearchableSelect 的选择器

### 1.4 发现的问题

#### 严重：UiSelect 在对话框内被遮挡

UiSelect 浮层通过 SelectPortal teleport 到 body，z-index 为 900。UiDialog 同样 teleport 到 body，z-index 为 1000/1001。对话框内的 UiSelect 下拉面板渲染在对话框遮罩层**后面**，用户看不到也点不到。

受影响位置：

- `PageEditDialog.vue:86`：自动保存间隔选择
- `FontEditorDialog.vue:20,39,47,51`：字体资源、格式、样式、display（4 个）
- `UsersView.vue:78,81`：角色和状态选择
- `AssetsView.vue:258,286`：上传/新建对话框中的资源类型

SearchableSelect 不受影响（z-1600 > 1000）。

#### 中等：z-index 体系与 DESIGN.md 脱节

DESIGN.md §7.1 要求"浮层使用统一 z-index Token，不声明任意大数值"。`style.css` 定义了 Token（`--ui-z-dropdown: 30` 等），`tailwind.config.js` 也映射了对应工具类（`z-dropdown` 等），但**没有任何组件使用**。实际用的是 z-[900]、z-[1600]、z-[1700]、z-[1800] 等任意值。

#### 中等：click-outside 逻辑重复 4 次

UserMenu、WorkspaceSwitcher、ProjectQuickSwitcher、AgentSessionControls 各自内联了一份几乎相同的 `vClickOutside` 指令。composables 和 utils 中没有共享版本。

#### 轻微：UiSelect 与 SearchableSelect 职责重叠

两者都支持单选/多选，能力边界模糊。SearchableSelect 多了搜索、清空、描述文本、关键词匹配；UiSelect 更轻量但没有搜索。选择哪个全靠开发者直觉。

### 1.5 Reka UI 2.10.1 API 摸底结论

| 能力 | 结论 |
|---|---|
| SelectRoot `multiple` | 支持 |
| ComboboxRoot `ignore-filter` | 支持，可跳过内置过滤，由组件自行控制 |
| ComboboxInput `displayValue` | 支持，选中后输入框显示 label |
| ComboboxInput `modelValue` | 即搜索词，可受控 |
| ComboboxInput 输入时自动展开 | 是（handleInput 中 onOpenChange(true)） |
| ComboboxContent `position="popper"` | 支持，与 Popover/DropdownMenu 同定位方式 |
| ComboboxCancel | 存在，可用于 clearable 清空按钮 |
| ComboboxRoot `openOnClick` / `openOnFocus` | 默认 false，输入时仍自动展开 |

---

## 2. 实施计划

### 目标

所有下拉统一基于 Reka UI 原语，消灭手写浮层定位和重复 click-outside，z-index 使用统一 Token。

### 步骤

| # | 步骤 | 依赖 | 状态 |
|---|---|---|---|
| 1 | z-index 体系统一：调整 style.css Token 值（dropdown/popover > dialog），改造所有 Teleport 浮层引用 Token | 无 | **进行中** |
| 2 | 增强 UiCombobox：描述/关键词过滤、多选标签 +N 折叠、clearable、compact 尺寸、选项描述渲染 | 步骤 1 | 待开始 |
| 3 | 迁移 SearchableSelect 20 处调用 → UiCombobox，保持 placeholder/empty-text 不变 | 步骤 2 | 待开始 |
| 4 | 扩展 UiDropdownMenu：图标、分隔线、danger、active 指示 | 步骤 1 | 待开始 |
| 5 | 替换 PaginationControl 原生 `<select>` → UiSelect | 步骤 1 | 待开始 |
| 6 | 替换 PlacementToolbar inline 单位下拉 → UiDropdownMenu，删除手写浮层代码 | 步骤 4 | 待开始 |
| 7 | 替换 AgentConversationPanel 模型菜单 → UiDropdownMenu，删除手动监听 | 步骤 4 | 待开始 |
| 8 | 替换 UserMenu → UiDropdownMenu（图标+分隔线），删除内联 click-outside | 步骤 4 | 待开始 |
| 9 | 替换 WorkspaceSwitcher / ProjectQuickSwitcher / AgentSessionControls → UiPopover（非受控），删除 3 份 click-outside | 步骤 1 | 待开始 |
| 10 | 替换 PreviewSizePresetSelect 手写浮层 → UiPopover，删除定位/click-outside 代码 | 步骤 1 | 待开始 |
| 11 | 清理死代码：删除 SearchableSelect.vue 及其测试，更新所有测试 stub | 步骤 3 | 待开始 |
| 12 | 补充 UiCombobox 单测（过滤/多选/清空/禁用/空态） | 步骤 2 | 待开始 |
| 13 | 文档：docs/developer 补充下拉组件选型与 z-index 层级说明 | 步骤 11 | 待开始 |
| 14 | 验证：test:editor + test:editor:gate，报告已跑/未跑测试 | 全部 | 待开始 |

---

## 3. 当前进度

### 已完成

**z-index Token 值调整**（style.css）：

```
改前：--ui-z-dropdown: 30; --ui-z-popover: 40; --ui-z-dialog: 50; --ui-z-toast: 60;
改后：--ui-z-dialog: 1000; --ui-z-dropdown: 1100; --ui-z-popover: 1100; --ui-z-toast: 1200;
```

新增 `--ui-z-confirm-overlay: 1050`（确认弹窗介于 dialog 和 dropdown 之间）。

**tailwind.config.js**：新增 `'confirm-overlay': 'var(--ui-z-confirm-overlay)'` 映射。

**已改为 Token 引用的组件**（9 个文件已修改，见 git status）：

| 文件 | 改动 |
|---|---|
| `UiSelect.vue` | z-[900] → z-dropdown |
| `UiCombobox.vue` | z-[900] → z-dropdown |
| `UiDropdownMenu.vue` | z-[900] → z-dropdown |
| `UiPopover.vue` | z-[900] → z-popover |
| `UiTooltip.vue` | z-[900] → z-popover |
| `UiDialog.vue` | shell z-[1000] → z-dialog（panel z-[1001] 待处理） |
| `message.ts` | Toast z-[2000] → z-toast；确认弹窗 z-[1100] → z-confirm-overlay |
| `style.css` | Token 值调整 |
| `tailwind.config.js` | 新增 confirm-overlay 映射 |

### 未完成 / 遗留

| 项目 | 说明 |
|---|---|
| UiDialog panel z-[1001] | 仍为硬编码，需改为 `z-[calc(var(--ui-z-dialog)+1)]` 或新增 Token |
| SearchableSelect z-[1600] | 待 UiCombobox 替换后随文件删除 |
| PlacementToolbar z-[1800] | 待步骤 6 替换后删除 |
| PreviewSizePresetSelect z-[1700] | 待步骤 10 替换后删除 |
| UiCombobox 增强重写 | 新文件内容已准备好但因转义问题未写入磁盘 |
| 步骤 3–14 | 全部待开始 |

### 注意事项

- 所有改动尚未提交 git，当前为工作区未暂存修改。
- 未运行任何测试，z-index 改动需要 `test:editor` 验证无回归。
- `SplitPane.vue` 引用了 `--ui-z-base` 变量，该变量在 style.css 中**不存在**，是既有问题，不在本次治理范围内。

