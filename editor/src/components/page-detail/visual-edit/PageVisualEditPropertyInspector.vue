<!-- 文件功能：展示选中 Vue 节点的内容、组件参数与受限 Tailwind 样式，并生成本地可视化编辑草稿。 -->
<template>
  <ToolPanel
    class="min-h-0 rounded-none border-y-0 border-r-0"
    :title="inspectorTitle"
    :description="props.node ? inspectorSubtitle : '点击画布中的文字、区块或组件进行编辑。'"
  >
    <template #header>
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h3 class="truncate text-title-sm font-semibold text-[rgb(var(--ui-text))]" :title="inspectorTitle">{{ inspectorTitle }}</h3>
          <p class="mt-0.5 truncate text-xs text-[rgb(var(--ui-text-muted))]">{{ props.node ? inspectorSubtitle : '点击画布中的文字、区块或组件进行编辑。' }}</p>
        </div>
        <div v-if="props.node && showTemplateActions" class="flex shrink-0 items-center gap-1">
          <UiIconButton
            v-if="props.node.template_actions.can_duplicate"
            :label="`复制${nodeTypeLabel}`"
            size="sm"
            @click="requestStructure('duplicate_node', templateTarget, `复制${nodeTypeLabel}`)"
          ><Copy class="h-4 w-4" /></UiIconButton>
          <UiIconButton
            v-if="props.node.template_actions.can_delete"
            :label="props.node.loop_context ? '删除整个循环结构' : `删除${nodeTypeLabel}`"
            variant="danger"
            size="sm"
            @click="requestStructure('delete_node', templateTarget, props.node.loop_context ? '删除整个循环结构' : `删除${nodeTypeLabel}`)"
          ><Trash2 class="h-4 w-4" /></UiIconButton>
          <UiButton
            v-if="pendingTemplateOperation"
            variant="ghost"
            size="xs"
            @click="emit('remove-structure', templateTarget)"
          >撤销</UiButton>
        </div>
      </div>
    </template>

    <div v-if="props.node" class="space-y-3">
      <InspectorSection v-if="props.node.loop_context" title="循环容器" :collapsible="false">
        <p class="font-semibold">循环容器</p>
        <p class="mt-1 break-all">{{ props.node.loop_context.source_expression }}</p>
        <p v-if="!props.node.loop_context.editable" class="mt-2 text-warning-strong">
          {{ readonlyReasonLabel(props.node.loop_context.readonly_reason) }}
        </p>
      </InspectorSection>

      <InspectorSection v-if="loopItemActions" title="循环实例">
        <PropertyRow label="当前实例" for-id="visual-edit-instance" description="操作集合中对应的数据项。">
        <UiSelect
          v-model="selectedLocationIndex"
          id="visual-edit-instance"
          aria-label="当前重复项"
          :options="loopItemActions.instances.map(location => ({ value: location.index, label: instanceLabel(location) }))"
        />
        </PropertyRow>
        <div class="mt-3 flex gap-2">
          <UiButton
            v-if="loopItemActions.can_duplicate"
            class="flex-1"
            variant="secondary"
            size="sm"
            @click="requestStructure('duplicate_node', loopItemTarget, '复制此项')"
          >复制此项</UiButton>
          <UiButton
            v-if="loopItemActions.can_delete"
            class="flex-1"
            variant="danger"
            size="sm"
            @click="requestStructure('delete_node', loopItemTarget, '删除此项')"
          >删除此项</UiButton>
          <UiButton
            v-if="pendingStructureOperation"
            variant="ghost"
            size="sm"
            @click="removePendingStructure"
          >撤销</UiButton>
        </div>
      </InspectorSection>

      <InspectorSection v-if="jsonBindingViews.length" title="结构化数据">
        <PageVisualEditJsonField
          v-for="item in jsonBindingViews"
          :key="item.source.source_id"
          :source="item.source"
          :label="item.label"
          :component-prop="item.componentProp"
          :pending-value="jsonPendingValue(item.source.source_id)"
          @set-json="emit('set-json', $event)"
          @validation-change="emit('json-validation', $event)"
        />
      </InspectorSection>

      <details class="rounded-ui-md border border-border bg-surface-muted px-3 py-2 text-xs text-text-muted">
        <summary class="cursor-pointer font-medium outline-none focus-visible:ring-2 focus-visible:ring-border-focus">
          技术详情
        </summary>
        <dl class="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1">
          <dt>源码标签</dt>
          <dd class="min-w-0 break-all font-mono">{{ props.node.tag }}</dd>
          <dt>节点标识</dt>
          <dd class="min-w-0 break-all font-mono">{{ props.node.node_id }}</dd>
          <template v-if="props.selectedBindingId">
            <dt>绑定标识</dt>
            <dd class="min-w-0 break-all font-mono">{{ props.selectedBindingId }}</dd>
          </template>
        </dl>
      </details>

      <div
        v-if="isNativeImageNode"
        class="rounded-lg border border-warning-border bg-warning-muted px-3 py-4 text-xs leading-5 text-warning-strong"
      >
        原生图片不提供低代码内容编辑。请改用 AssetImage.v1 图片组件，或通过 AI / 高级源码调整图片资源与展示方式。
      </div>

      <template v-else-if="hasRenderableBindings">
        <PageVisualEditAssetImageInspector
          v-if="componentInspectorKey === 'asset-image-v1'"
          :workspace-id="workspaceId"
          :fields="assetImageFieldViews"
          :style="assetImageStyleView"
          @select="selectBindingById"
          @set-value="handleAssetImageValueChange"
          @set-tailwind="handleAssetImageTailwindChange"
        />

        <template v-else-if="showComponentPropForm">
          <InspectorSection v-if="componentPropBindings.length" title="组件参数">
            <template #actions>
              <span class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-semibold text-text-muted">
                {{ componentPropBindings.length }} 项
              </span>
            </template>
            <PageVisualEditValueField
              v-for="binding in componentPropBindings"
              :key="binding.binding_id"
              :control-id="bindingControlId(binding)"
              :control-type="bindingControlType(binding)"
              :baseline-value="bindingBaselineValue(binding)"
              :baseline-rich-text="binding.kind === 'rich_text' ? String(bindingBaselineValue(binding) ?? '') : null"
              :description="bindingPropField(binding)?.description ?? null"
              :editable="isBindingValueEditable(binding)"
              :effective-value="bindingEffectiveValue(binding)"
              :kind="binding.kind"
              :label="bindingLabel(binding)"
              :option-index="bindingSelectedOptionIndex(binding)"
              :options="bindingPropField(binding)?.options ?? []"
              :pending="hasCurrentOperation(binding)"
              :placeholder="bindingPropField(binding)?.placeholder ?? null"
              :prop-name="binding.name ?? null"
              :readonly-message="bindingReadonlyMessage(binding)"
              :required="Boolean(bindingPropField(binding)?.required)"
              :selected="isSelectedBinding(binding)"
              :template-literal-warning="shouldShowTemplateLiteralWarning(binding)"
              @select="selectBinding(binding)"
              @set-rich-text="html => stageRichText(binding, html)"
              @set-value="value => stageValue(binding, value)"
            />
          </InspectorSection>

          <InspectorSection v-if="styleBindings.length" title="组件样式">
            <template #actions>
              <span class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-semibold text-text-muted">
                {{ styleBindings.length }} 项
              </span>
            </template>
            <PageVisualEditTailwindStyleEditor
              v-for="binding in styleBindings"
              :key="binding.binding_id"
              :binding-id="binding.binding_id"
              :editable="isTailwindEditable(binding)"
              :groups="tailwindGroupViewsForBinding(binding)"
              :pending="hasCurrentOperation(binding)"
              :readonly-message="classReadonlyMessageForBinding(binding)"
              :template-literal-warning="shouldShowTemplateLiteralWarning(binding)"
              :unknown-tokens="unknownClassTokensForBinding(binding)"
              :common-group-keys="commonTailwindGroupKeys"
              @change="payload => handleTailwindGroupChange(binding, payload.group, payload.className)"
              @select="selectBinding(binding)"
            />
          </InspectorSection>
        </template>

        <template v-else>
          <UiTabs
            v-if="structureTabs.length"
            v-model="activeStructureTab"
            :items="structureTabItems"
            list-class="mb-4"
          >
            <template #content>
              <section class="space-y-3">
                <PageVisualEditValueField
                  v-for="binding in contentBindings"
                  :key="binding.binding_id"
                  :control-id="bindingControlId(binding)"
                  :control-type="bindingControlType(binding)"
                  :baseline-value="bindingBaselineValue(binding)"
                  :baseline-rich-text="binding.kind === 'rich_text' ? String(bindingBaselineValue(binding) ?? '') : null"
                  :editable="isBindingValueEditable(binding)"
                  :effective-value="bindingEffectiveValue(binding)"
                  :kind="binding.kind"
                  :label="bindingLabel(binding)"
                  :option-index="bindingSelectedOptionIndex(binding)"
                  :options="[]"
                  :pending="hasCurrentOperation(binding)"
                  :readonly-message="bindingReadonlyMessage(binding)"
                  :required="false"
                  :rows="5"
                  :selected="isSelectedBinding(binding)"
                  :template-literal-warning="shouldShowTemplateLiteralWarning(binding)"
                  @select="selectBinding(binding)"
                  @set-rich-text="html => stageRichText(binding, html)"
                  @set-value="value => stageValue(binding, value)"
                />
              </section>
            </template>

            <template #style>
              <section class="space-y-3">
                <PageVisualEditTailwindStyleEditor
                  v-for="binding in styleBindings"
                  :key="binding.binding_id"
                  :binding-id="binding.binding_id"
                  :editable="isTailwindEditable(binding)"
                  :groups="tailwindGroupViewsForBinding(binding)"
                  :pending="hasCurrentOperation(binding)"
                  :readonly-message="classReadonlyMessageForBinding(binding)"
                  :template-literal-warning="shouldShowTemplateLiteralWarning(binding)"
                  :unknown-tokens="unknownClassTokensForBinding(binding)"
                  :common-group-keys="commonTailwindGroupKeys"
                  @change="payload => handleTailwindGroupChange(binding, payload.group, payload.className)"
                  @select="selectBinding(binding)"
                />
              </section>
            </template>
          </UiTabs>
        </template>
      </template>

      <p v-else class="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-text-disabled">
        {{ emptyStateText }}
      </p>
    </div>
    <DataState
      v-else
      state="empty"
      title="未选择编辑对象"
      description="点击画布中的文字、区块或组件后，在这里修改内容、参数和样式。"
    />
  </ToolPanel>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Copy, Trash2 } from '@lucide/vue'

import InspectorSection from '@/components/patterns/InspectorSection.vue'
import PropertyRow from '@/components/patterns/PropertyRow.vue'
import DataState from '@/components/patterns/DataState.vue'
import PageVisualEditAssetImageInspector from '@/components/page-detail/visual-edit/PageVisualEditAssetImageInspector.vue'
import PageVisualEditTailwindStyleEditor from '@/components/page-detail/visual-edit/PageVisualEditTailwindStyleEditor.vue'
import PageVisualEditValueField from '@/components/page-detail/visual-edit/PageVisualEditValueField.vue'
import PageVisualEditJsonField from '@/components/page-detail/visual-edit/PageVisualEditJsonField.vue'
import ToolPanel from '@/components/patterns/ToolPanel.vue'
import { UiButton, UiIconButton, UiSelect, UiTabs } from '@/components/ui'
import type {
  PageVisualEditBinding,
  PageVisualEditComponentPropField,
  PageVisualEditComponentSchema,
  PageVisualEditInstancePathSegment,
  PageVisualEditJsonSource,
  PageVisualEditJsonValue,
  PageVisualEditLoopItemActions,
  PageVisualEditLoopItemLocation,
  PageVisualEditNodeTarget,
  PageVisualEditNode,
  PageVisualEditOperation,
  PageVisualEditScriptArrayBindingSource,
  PageVisualEditScriptMemberLocation,
  PageVisualEditTailwindCatalog,
  PageVisualEditTailwindTokenChange,
  PageVisualEditTarget,
  PageVisualEditValue,
  PageVisualEditValueType,
} from '@/types/page-visual-edit'
import {
  resolvePageVisualEditComponentPropField,
  resolvePageVisualEditComponentSchema,
} from '@/utils/page-visual-edit'
import {
  ASSET_IMAGE_PROP_NAMES,
  ASSET_IMAGE_STYLE_GROUP_KEYS,
  resolvePageVisualEditComponentInspector,
} from '@/components/page-detail/visual-edit/page-visual-edit-component-inspectors'

type StructureTabKey = 'content' | 'style'

const props = defineProps<{
  node: PageVisualEditNode | null
  selectedBindingId: string
  selectedInstancePath: PageVisualEditInstancePathSegment[]
  loopNodeId: string
  catalog: PageVisualEditTailwindCatalog | null
  componentSchemas: Record<string, PageVisualEditComponentSchema>
  jsonSources: PageVisualEditJsonSource[]
  pendingOperations: PageVisualEditOperation[]
  workspaceId?: number | null
}>()

const emit = defineEmits<{
  'select-binding': [bindingId: string]
  'set-value': [payload: { target: PageVisualEditTarget; value: PageVisualEditValue; baselineValue: PageVisualEditValue | undefined }]
  'set-json': [payload: { sourceId: string; value: PageVisualEditJsonValue; baselineValue: PageVisualEditJsonValue }]
  'json-validation': [payload: { sourceId: string; invalid: boolean }]
  'set-rich-text': [payload: { target: PageVisualEditTarget; html: string; baselineHtml: string }]
  'set-tailwind': [payload: {
    target: PageVisualEditTarget
    changes: PageVisualEditTailwindTokenChange[]
    baselineChanges: PageVisualEditTailwindTokenChange[]
  }]
  'set-structure': [payload: { type: 'duplicate_node' | 'delete_node'; target: PageVisualEditNodeTarget; label: string }]
  'remove-structure': [target: PageVisualEditNodeTarget]
  'select-instance': [path: PageVisualEditInstancePathSegment[]]
}>()

const selectedLocationIndex = ref(0)
const activeStructureTab = ref<StructureTabKey>('content')
const paragraphTags = new Set(['p', 'span', 'strong', 'em', 'small', 'label', 'li', 'dt', 'dd', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
const textCommonTailwindGroupKeys = ['text-size', 'font-weight', 'text-alignment', 'line-height', 'text-color']
const containerCommonTailwindGroupKeys = [
  'flex-direction',
  'items',
  'justify',
  'gap',
  'padding',
  'background-color',
  'border-width',
  'border-style',
  'border-color',
  'radius',
  'shadow',
]

const componentSchema = computed(() => resolvePageVisualEditComponentSchema(props.node, props.componentSchemas))
const componentInspectorKey = computed(() => resolvePageVisualEditComponentInspector(componentSchema.value))
const nodeBindings = computed(() => props.node?.bindings ?? [])
const selectedBinding = computed(() => (
  nodeBindings.value.find(binding => binding.binding_id === props.selectedBindingId) ?? null
))
const componentPropBindings = computed(() => nodeBindings.value.filter(binding => (
  binding.kind === 'prop' && binding.source?.kind !== 'json-source'
)))
const contentBindings = computed(() => nodeBindings.value.filter(binding => binding.kind === 'text' || binding.kind === 'rich_text'))
const styleBindings = computed(() => nodeBindings.value.filter(binding => binding.kind === 'class'))
const showComponentPropForm = computed(() => props.node?.kind === 'component' && componentPropBindings.value.length > 0)
const isNativeImageNode = computed(() => props.node?.kind === 'element' && props.node.tag.toLowerCase() === 'img')
const workspaceId = computed(() => (
  Number.isInteger(props.workspaceId) && Number(props.workspaceId) > 0
    ? Number(props.workspaceId)
    : null
))
const commonTailwindGroupKeys = computed(() => (
  props.node && isParagraphLikeNode(props.node)
    ? textCommonTailwindGroupKeys
    : containerCommonTailwindGroupKeys
))
const structureTabs = computed<Array<{ key: StructureTabKey; label: string }>>(() => {
  const tabs: Array<{ key: StructureTabKey; label: string }> = []
  if (contentBindings.value.length) tabs.push({ key: 'content', label: '内容' })
  if (styleBindings.value.length) tabs.push({ key: 'style', label: '样式' })
  return tabs
})
const structureTabItems = computed(() => (
  structureTabs.value.map(tab => ({ value: tab.key, label: tab.label }))
))
const hasRenderableBindings = computed(() => {
  if (componentInspectorKey.value === 'asset-image-v1') return true
  if (showComponentPropForm.value) return componentPropBindings.value.length > 0 || styleBindings.value.length > 0
  return structureTabs.value.length > 0
})
const assetImageFieldViews = computed(() => componentPropBindings.value
  .filter(binding => ASSET_IMAGE_PROP_NAMES.includes(binding.name as typeof ASSET_IMAGE_PROP_NAMES[number]))
  .map(binding => ({
    name: binding.name as typeof ASSET_IMAGE_PROP_NAMES[number],
    bindingId: binding.binding_id,
    value: bindingEffectiveValue(binding),
    baselineValue: bindingBaselineValue(binding),
    editable: isAssetImageStaticBinding(binding) && isBindingValueEditable(binding),
    pending: hasCurrentOperation(binding),
    readonlyMessage: assetImageReadonlyMessage(binding),
    selected: isSelectedBinding(binding),
    templateLiteralWarning: shouldShowTemplateLiteralWarning(binding),
  })))
const assetImageStyleView = computed(() => {
  const binding = styleBindings.value[0]
  if (!binding) return null
  return {
    bindingId: binding.binding_id,
    editable: isAssetImageStaticBinding(binding) && isTailwindEditable(binding),
    groups: tailwindGroupViewsForBinding(binding),
    pending: hasCurrentOperation(binding),
    readonlyMessage: assetImageClassReadonlyMessage(binding),
    templateLiteralWarning: shouldShowTemplateLiteralWarning(binding),
    unknownTokens: unknownClassTokensForBinding(binding),
  }
})
const assetImageDisplayName = computed(() => {
  const preferredNames = ['alt', 'name']
  for (const name of preferredNames) {
    const field = assetImageFieldViews.value.find(item => item.name === name)
    if (typeof field?.value === 'string' && field.value.trim()) {
      const normalizedValue = field.value.trim()
      return normalizedValue.length > 18 ? `${normalizedValue.slice(0, 18)}…` : normalizedValue
    }
  }
  return ''
})
const loopItemActions = computed<PageVisualEditLoopItemActions | null>(() => props.node?.loop_item_actions ?? null)
const jsonBindingViews = computed(() => nodeBindings.value.flatMap((binding) => {
  const bindingSource = binding.source
  if (bindingSource?.kind !== 'json-source') return []
  const source = props.jsonSources.find(item => item.source_id === bindingSource.source_id)
  if (!source) return []
  const componentProp = binding.kind === 'prop'
  if (componentProp && bindingPropField(binding)?.type !== 'json') return []
  return [{
    source,
    componentProp,
    label: componentProp ? bindingPropField(binding)?.label || binding.name || 'JSON 参数' : binding.name || '数据',
  }]
}))
const fallbackScriptSource = computed<PageVisualEditScriptArrayBindingSource | null>(() => (
  nodeBindings.value.map(bindingScriptSource).find(Boolean) ?? null
))
const selectedLoopLocation = computed<PageVisualEditLoopItemLocation | null>(() => (
  loopItemActions.value?.instances.find(item => item.index === selectedLocationIndex.value)
  ?? loopItemActions.value?.instances[0]
  ?? null
))
const templateTarget = computed<PageVisualEditNodeTarget>(() => ({ nodeId: props.node?.node_id ?? '', instancePath: [] }))
const loopItemTarget = computed<PageVisualEditNodeTarget>(() => {
  const actions = loopItemActions.value
  const location = selectedLoopLocation.value
  return {
    nodeId: props.node?.node_id ?? '',
    instancePath: actions && location ? [{ loopNodeId: actions.loop_node_id, key: location.key, index: location.index }] : [],
  }
})
const pendingStructureOperation = computed(() => props.pendingOperations.find(operation => (
  (operation.type === 'duplicate_node' || operation.type === 'delete_node')
  && sameNodeTarget(operation, loopItemTarget.value)
)) ?? null)
const pendingTemplateOperation = computed(() => props.pendingOperations.find(operation => (
  (operation.type === 'duplicate_node' || operation.type === 'delete_node')
  && sameNodeTarget(operation, templateTarget.value)
)) ?? null)
const showTemplateActions = computed(() => Boolean(
  props.node?.template_actions?.can_duplicate || props.node?.template_actions?.can_delete,
))
const nodeTypeLabel = computed(() => {
  if (props.node?.kind === 'component') return '组件'
  if (props.node && isParagraphLikeNode(props.node)) return '段落'
  return '结构'
})
const nodeDeleted = computed(() => props.pendingOperations.some(operation => (
  operation.type === 'delete_node'
  && (sameNodeTarget(operation, templateTarget.value) || sameNodeTarget(operation, loopItemTarget.value))
)))
const inspectorTitle = computed(() => {
  const node = props.node
  if (!node) return '未选择'
  if (componentInspectorKey.value === 'asset-image-v1') {
    return assetImageDisplayName.value ? `图片：${assetImageDisplayName.value}` : '图片'
  }
  return semanticNodeTitle(node)
})
const inspectorSubtitle = computed(() => {
  const node = props.node
  if (!node) return ''
  const segments = [inspectorScopeLabel.value]
  if (componentInspectorKey.value === 'asset-image-v1') segments.push('工作空间图片')
  if (componentPropBindings.value.length) segments.push(`${componentPropBindings.value.length} 项参数`)
  if (contentBindings.value.length) segments.push(`${contentBindings.value.length} 项内容`)
  if (styleBindings.value.length) segments.push(`${styleBindings.value.length} 组样式`)
  return segments.join(' · ')
})
const inspectorScopeLabel = computed(() => {
  if (!props.node?.loop_context) return '当前元素'
  if (selectedBinding.value?.source?.kind === 'template-literal') return '全部重复项'
  return props.selectedInstancePath.length ? '当前重复项' : '全部重复项'
})
const emptyStateText = computed(() => {
  const node = props.node
  if (!node) return '请选择一个容器。'
  if (node.kind === 'component') return '此组件没有可展示参数或样式。'
  if (isParagraphLikeNode(node)) return '此段落没有可编辑内容或样式。'
  return '此结构没有可编辑内容或样式。'
})
const catalogClassNames = computed(() => new Set(
  (props.catalog?.groups ?? []).flatMap(group => group.options.map(option => option.class_name)),
))

watch(
  [loopItemActions, fallbackScriptSource, () => props.selectedInstancePath],
  ([actions, fallback, instancePath]) => {
    const locations = actions?.instances ?? fallback?.locations ?? []
    if (!locations.length) return
    const runtimeSegment = instancePath.find(segment => segment.loopNodeId === (actions?.loop_node_id ?? props.loopNodeId))
    const matched = locations.find(location => (
      runtimeSegment?.key !== undefined
        ? location.key === runtimeSegment.key
        : location.index === runtimeSegment?.index
    ))
    selectedLocationIndex.value = (matched ?? locations[0])!.index
  },
  { immediate: true },
)

watch(selectedLoopLocation, (location) => {
  const actions = loopItemActions.value
  if (!actions || !location) return
  emit('select-instance', [{ loopNodeId: actions.loop_node_id, key: location.key, index: location.index }])
})

watch(
  () => structureTabs.value.map(tab => tab.key).join('|'),
  () => {
    if (!structureTabs.value.some(tab => tab.key === activeStructureTab.value)) {
      activeStructureTab.value = structureTabs.value[0]?.key ?? 'content'
    }
  },
  { immediate: true },
)

/** 判断节点是否以段落或文本内容编辑为主。 */
function isParagraphLikeNode(node: PageVisualEditNode): boolean {
  return paragraphTags.has(node.tag.toLowerCase()) || node.bindings.some(binding => binding.kind === 'text' || binding.kind === 'rich_text')
}

/** 使用内容职责和静态短文本生成属性面板标题，源码标签只进入技术详情。 */
function semanticNodeTitle(node: PageVisualEditNode): string {
  if (node.kind === 'root') return '页面'
  if (node.kind === 'component') {
    return `组件：${componentSchema.value?.component_code || '自定义组件'}`
  }
  const tag = node.tag.toLowerCase()
  const text = nodeTextSnippet(node)
  if (/^h[1-6]$/.test(tag)) return labelWithSnippet('标题', text)
  if (tag === 'img') return '原生图片'
  if (['p', 'span', 'strong', 'em', 'small', 'label', 'li', 'dt', 'dd', 'blockquote'].includes(tag)) {
    return labelWithSnippet('文本', text)
  }
  if (tag === 'button') return labelWithSnippet('按钮', text)
  if (tag === 'a') return labelWithSnippet('链接', text)
  if (['section', 'article', 'main', 'header', 'footer', 'nav', 'aside'].includes(tag)) return '区块'
  if (tag === 'div') return '容器'
  return '元素'
}

/** 从当前节点的可编辑内容中读取短文本，待保存值优先于页面版本原值。 */
function nodeTextSnippet(node: PageVisualEditNode): string {
  for (const binding of node.bindings) {
    if (binding.kind !== 'text' && binding.kind !== 'rich_text') continue
    const value = bindingEffectiveValue(binding)
    if (typeof value !== 'string') continue
    const normalized = value.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
    if (!normalized) continue
    const characters = Array.from(normalized)
    return characters.length > 18 ? `${characters.slice(0, 18).join('')}…` : normalized
  }
  return ''
}

/** 为语义节点标题追加可读短内容。 */
function labelWithSnippet(label: string, snippet: string): string {
  return snippet ? `${label}：${snippet}` : label
}

/** 选择当前操作的绑定，用于保持画布定位与循环实例上下文一致。 */
function selectBinding(binding: PageVisualEditBinding): void {
  if (binding.binding_id !== props.selectedBindingId) {
    emit('select-binding', binding.binding_id)
  }
}

/** 按 binding id 同步专用检查器的当前字段，不接受不存在的伪造目标。 */
function selectBindingById(bindingId: string): void {
  const binding = nodeBindings.value.find(item => item.binding_id === bindingId)
  if (binding) selectBinding(binding)
}

/** 将 AssetImage 专用字段事件收窄到已注册的四个静态 prop。 */
function handleAssetImageValueChange(payload: { bindingId: string; value: PageVisualEditValue }): void {
  const binding = componentPropBindings.value.find(item => (
    item.binding_id === payload.bindingId
    && ASSET_IMAGE_PROP_NAMES.includes(item.name as typeof ASSET_IMAGE_PROP_NAMES[number])
  ))
  if (!binding || !isAssetImageStaticBinding(binding)) return
  stageValue(binding, payload.value)
}

/** 将 AssetImage 图片框样式限制在明确允许的冲突组内。 */
function handleAssetImageTailwindChange(payload: { bindingId: string; group: string; className: string }): void {
  if (!ASSET_IMAGE_STYLE_GROUP_KEYS.includes(payload.group as typeof ASSET_IMAGE_STYLE_GROUP_KEYS[number])) return
  const binding = styleBindings.value.find(item => item.binding_id === payload.bindingId)
  if (!binding || !isAssetImageStaticBinding(binding)) return
  handleTailwindGroupChange(binding, payload.group, payload.className)
}

/** 判断某个绑定是否为当前画布选中的绑定。 */
function isSelectedBinding(binding: PageVisualEditBinding): boolean {
  return binding.binding_id === props.selectedBindingId
}

/** 生成人类可读的绑定名称。 */
function bindingLabel(binding: PageVisualEditBinding): string {
  if (binding.kind === 'text') return '文本内容'
  if (binding.kind === 'rich_text') return '段落内容'
  if (binding.kind === 'class') return 'Tailwind 样式'
  const schemaLabel = binding.kind === 'prop' && binding.name
    ? resolvePageVisualEditComponentPropField(componentSchema.value, binding.name)?.label
    : null
  return schemaLabel || (binding.name ? `组件参数 · ${binding.name}` : '组件参数')
}

/** 展示脚本数组实例的稳定 key，并保留 index 作为辅助定位信息。 */
function instanceLabel(location: PageVisualEditScriptMemberLocation | PageVisualEditLoopItemLocation): string {
  return location.key !== null && location.key !== undefined
    ? `key: ${String(location.key)}（第 ${location.index + 1} 项）`
    : `第 ${location.index + 1} 项`
}

/** 生成绑定控件的稳定 DOM id。 */
function bindingControlId(binding: PageVisualEditBinding): string {
  return `visual-edit-binding-${safeDomId(binding.binding_id)}`
}

/** DOM id 只保留安全字符，避免绑定 id 中的分隔符影响 label 关联。 */
function safeDomId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-')
}

/** 读取组件 prop 的 schema 字段。 */
function bindingPropField(binding: PageVisualEditBinding): PageVisualEditComponentPropField | null {
  if (binding.kind !== 'prop' || !binding.name) return null
  return resolvePageVisualEditComponentPropField(componentSchema.value, binding.name)
}

/** 读取绑定对应的脚本数组数据源。 */
function bindingScriptSource(binding: PageVisualEditBinding | null | undefined): PageVisualEditScriptArrayBindingSource | null {
  return binding?.source?.kind === 'script-array-item' ? binding.source : null
}

/** 在当前循环实例选择下读取绑定 location。 */
function bindingSelectedLocation(binding: PageVisualEditBinding): PageVisualEditScriptMemberLocation | null {
  const source = bindingScriptSource(binding)
  if (!source) return null
  return source.locations.find(item => item.index === selectedLocationIndex.value) ?? source.locations[0] ?? null
}

/** 按绑定和当前循环实例生成草稿目标。 */
function bindingTarget(binding: PageVisualEditBinding): PageVisualEditTarget | null {
  const source = bindingScriptSource(binding)
  if (!source) {
    return { nodeId: binding.node_id, bindingId: binding.binding_id, instancePath: [] }
  }
  const location = bindingSelectedLocation(binding)
  if (!location || !props.loopNodeId) return null
  if (!isStableInstanceKey(location.key)) return null
  const segment: PageVisualEditInstancePathSegment = {
    loopNodeId: props.loopNodeId,
    key: location.key,
    index: location.index,
  }
  return { nodeId: binding.node_id, bindingId: binding.binding_id, instancePath: [segment] }
}

/** 查找绑定当前未保存操作。 */
function bindingCurrentOperation(binding: PageVisualEditBinding): PageVisualEditOperation | null {
  const editTarget = bindingTarget(binding)
  if (!editTarget) return null
  return props.pendingOperations.find(operation => (
    operation.type !== 'set_json'
    &&
    operation.type !== 'duplicate_node'
    && operation.type !== 'delete_node'
    && sameTarget(operation, editTarget)
  )) ?? null
}

/** 读取 JSON source 当前待保存值；不存在操作时让子组件回退 artifact 基准。 */
function jsonPendingValue(sourceId: string): PageVisualEditJsonValue | undefined {
  const operation = props.pendingOperations.find(item => item.type === 'set_json' && item.sourceId === sourceId)
  return operation?.type === 'set_json' ? operation.value : undefined
}

/** 判断绑定是否存在未保存操作。 */
function hasCurrentOperation(binding: PageVisualEditBinding): boolean {
  return Boolean(bindingCurrentOperation(binding))
}

/** 读取绑定规范源码中的基准值。 */
function bindingBaselineValue(binding: PageVisualEditBinding): PageVisualEditValue | undefined {
  if (bindingScriptSource(binding)) return bindingSelectedLocation(binding)?.value
  return binding.value === null || ['string', 'number', 'boolean'].includes(typeof binding.value)
    ? binding.value as PageVisualEditValue
    : undefined
}

/** 读取绑定在本地草稿中的生效值。 */
function bindingEffectiveValue(binding: PageVisualEditBinding): PageVisualEditValue | undefined {
  const operation = bindingCurrentOperation(binding)
  if (operation?.type === 'set_value') return operation.value
  if (operation?.type === 'set_rich_text') return operation.html
  return bindingBaselineValue(binding)
}

/** 根据当前实例实际值推断控件需要消费的字面量类型。 */
function bindingEffectiveValueType(binding: PageVisualEditBinding): PageVisualEditValueType {
  if (!bindingScriptSource(binding)) return binding.value_type ?? 'unknown'
  const value = bindingSelectedLocation(binding)?.value
  if (value === null) return 'null'
  if (typeof value === 'string') return 'string'
  if (typeof value === 'number') return 'number'
  if (typeof value === 'boolean') return 'boolean'
  return 'unknown'
}

/** 选择绑定的表单控件类型，组件 schema 优先于源码推断。 */
function bindingControlType(binding: PageVisualEditBinding): string {
  const field = bindingPropField(binding)
  if (field) return field.type
  if (binding.kind === 'text') return 'textarea'
  return bindingEffectiveValueType(binding)
}

/** 读取 select 控件中与当前原始值匹配的选项下标。 */
function bindingSelectedOptionIndex(binding: PageVisualEditBinding): number {
  return bindingPropField(binding)?.options?.findIndex(option => Object.is(option.value, bindingEffectiveValue(binding))) ?? -1
}

/** 判断源码字面量类型是否满足组件 schema 对该 prop 的要求。 */
function bindingSchemaTypeCompatible(binding: PageVisualEditBinding): boolean {
  const field = bindingPropField(binding)
  if (!field || field.type === 'json') return true
  const actualType = bindingEffectiveValueType(binding)
  if (field.type === 'string' || field.type === 'textarea') return actualType === 'string'
  if (field.type === 'number') return actualType === 'number'
  if (field.type === 'boolean') return actualType === 'boolean'
  if (!field.options?.length) return true
  return actualType !== 'unknown'
    && actualType !== 'null'
    && field.options.every(option => typeof option.value === actualType)
}

/** 判断当前绑定是否可用普通值控件写回。 */
function isBindingValueEditable(binding: PageVisualEditBinding): boolean {
  return !nodeDeleted.value
    && Boolean(binding.editable)
    && bindingSelectedLocationEditable(binding)
    && Boolean(bindingTarget(binding))
    && bindingEffectiveValueType(binding) !== 'unknown'
    && bindingEffectiveValueType(binding) !== 'null'
    && bindingControlType(binding) !== 'json'
    && bindingSchemaTypeCompatible(binding)
    && (bindingControlType(binding) !== 'select' || Boolean(bindingPropField(binding)?.options?.length))
}

/** 判断当前循环实例是否具备安全写回条件。 */
function bindingSelectedLocationEditable(binding: PageVisualEditBinding): boolean {
  const source = bindingScriptSource(binding)
  if (!source) return true
  const location = bindingSelectedLocation(binding)
  return location?.editable === true && isStableInstanceKey(location.key)
}

/** 解释普通值控件只读原因。 */
function bindingReadonlyMessage(binding: PageVisualEditBinding): string {
  const source = bindingScriptSource(binding)
  const location = bindingSelectedLocation(binding)
  if (source && !location?.editable) {
    return readonlyReasonLabel(location?.readonly_reason)
  }
  if (source && !isStableInstanceKey(location?.key)) {
    return '此数组项缺少稳定的字符串或整数 key，不能安全写回。'
  }
  const field = bindingPropField(binding)
  if (field?.type === 'json') {
    return 'JSON 参数首版仅展示，不支持可视化写回。'
  }
  if (field && !bindingSchemaTypeCompatible(binding)) {
    return '源码字面量类型与组件 schema 不一致，当前只读。'
  }
  if (field?.type === 'select' && !field.options?.length) {
    return '此参数没有可用的有限选项，当前只读。'
  }
  return readonlyReasonLabel(binding.readonly_reason)
}

/** AssetImage 内容仅允许直接模板字面量，脚本数组和其他动态来源必须交给 AI 或源码编辑。 */
function isAssetImageStaticBinding(binding: PageVisualEditBinding): boolean {
  return binding.source?.kind === 'template-literal'
}

/** 为 AssetImage 动态 prop 提供普通语言说明。 */
function assetImageReadonlyMessage(binding: PageVisualEditBinding): string {
  if (!isAssetImageStaticBinding(binding)) {
    return '此图片参数使用动态绑定，不能在这里安全修改。请使用 AI 或高级源码调整。'
  }
  return bindingReadonlyMessage(binding)
}

/** 为 AssetImage 动态 class 提供图片框语义的只读说明。 */
function assetImageClassReadonlyMessage(binding: PageVisualEditBinding): string {
  if (!isAssetImageStaticBinding(binding)) {
    return '图片框样式使用动态 class，不能在这里安全修改。请使用 AI 或高级源码调整。'
  }
  return classReadonlyMessageForBinding(binding)
}

/** 判断模板字面量在循环中写回时是否需要提示会影响全部实例。 */
function shouldShowTemplateLiteralWarning(binding: PageVisualEditBinding): boolean {
  return Boolean(props.loopNodeId) && binding.source?.kind === 'template-literal'
}

/** 发出一个带规范源码基准值的值变更。 */
function stageValue(binding: PageVisualEditBinding, value: PageVisualEditValue): void {
  const editTarget = bindingTarget(binding)
  if (!editTarget || !isBindingValueEditable(binding)) return
  emit('set-value', { target: editTarget, value, baselineValue: bindingBaselineValue(binding) })
}

/** 发出一个带规范化基准值的富文本草稿变更。 */
function stageRichText(binding: PageVisualEditBinding, html: string): void {
  const editTarget = bindingTarget(binding)
  if (!editTarget || !isBindingValueEditable(binding) || binding.kind !== 'rich_text') return
  const baselineValue = bindingBaselineValue(binding)
  emit('set-rich-text', {
    target: editTarget,
    html,
    baselineHtml: typeof baselineValue === 'string' ? baselineValue : '',
  })
}

/** 判断 Tailwind 绑定是否具备受限目录写回能力。 */
function isTailwindEditable(binding: PageVisualEditBinding): boolean {
  return !nodeDeleted.value
    && binding.kind === 'class'
    && Boolean(binding.editable)
    && bindingSelectedLocationEditable(binding)
    && Boolean(bindingTarget(binding))
    && typeof bindingBaselineValue(binding) === 'string'
    && Boolean(props.catalog?.groups.length)
}

/** 解释 class 绑定只读原因。 */
function classReadonlyMessageForBinding(binding: PageVisualEditBinding): string {
  if (typeof bindingBaselineValue(binding) !== 'string') return 'class 源码字面量不是字符串，当前只读。'
  if (!props.catalog?.groups.length) return '当前 Runtime 未提供 Tailwind 可视化目录，class 仅展示不可编辑。'
  return bindingReadonlyMessage(binding)
}

/** 生成 Tailwind 子组件消费的分组视图，并补齐当前 class 回显值。 */
function tailwindGroupViewsForBinding(binding: PageVisualEditBinding): Array<{
  key: string
  label: string
  selectedClass: string
  baselineClass: string
  options: Array<{ class_name: string; label: string }>
}> {
  return (props.catalog?.groups ?? []).map(group => ({
    key: group.key,
    label: group.label,
    selectedClass: selectedClassForGroup(binding, group.key),
    baselineClass: baselineClassForGroup(binding, group.key) ?? '',
    options: group.options,
  }))
}

/** 按 Tailwind 互斥组写入或清除一个受限 class。 */
function handleTailwindGroupChange(binding: PageVisualEditBinding, group: string, className: string): void {
  const editTarget = bindingTarget(binding)
  if (!editTarget || !isTailwindEditable(binding)) return
  emit('set-tailwind', {
    target: editTarget,
    changes: [{ group, className: className || null }],
    baselineChanges: [{ group, className: baselineClassForGroup(binding, group) }],
  })
}

/** 读取指定组当前草稿值；无草稿时回退到 artifact 基准 class。 */
function selectedClassForGroup(binding: PageVisualEditBinding, group: string): string {
  const operation = bindingCurrentOperation(binding)
  const pending = operation?.type === 'set_tailwind_tokens'
    ? operation.changes.find(change => change.group === group)
    : null
  return pending ? pending.className ?? '' : baselineClassForGroup(binding, group) ?? ''
}

/** 从基准 class tokens 中寻找指定目录组的选项。 */
function baselineClassForGroup(binding: PageVisualEditBinding, groupKey: string): string | null {
  const group = props.catalog?.groups.find(item => item.key === groupKey)
  return group?.options.find(option => baselineClassTokensForBinding(binding).includes(option.class_name))?.class_name ?? null
}

/** 读取 class 绑定源码基准值中的 token 列表。 */
function baselineClassTokensForBinding(binding: PageVisualEditBinding): string[] {
  const value = bindingBaselineValue(binding)
  return typeof value === 'string' ? value.split(/\s+/).filter(Boolean) : []
}

/** 读取不在可视化目录内的复杂或未知 class。 */
function unknownClassTokensForBinding(binding: PageVisualEditBinding): string[] {
  return baselineClassTokensForBinding(binding).filter(token => !catalogClassNames.value.has(token))
}

/** 比较两个草稿目标的节点、绑定和实例路径。 */
function sameTarget(left: PageVisualEditTarget, right: PageVisualEditTarget): boolean {
  return left.nodeId === right.nodeId
    && left.bindingId === right.bindingId
    && JSON.stringify(left.instancePath) === JSON.stringify(right.instancePath)
}

/** 比较两个节点结构目标。 */
function sameNodeTarget(left: PageVisualEditNodeTarget, right: PageVisualEditNodeTarget): boolean {
  return left.nodeId === right.nodeId && JSON.stringify(left.instancePath) === JSON.stringify(right.instancePath)
}

/** 发出结构草稿请求；无合法节点或循环实例时保持只读。 */
function requestStructure(
  type: 'duplicate_node' | 'delete_node',
  target: PageVisualEditNodeTarget,
  label: string,
): void {
  if (!target.nodeId || (label.endsWith('此项') && target.instancePath.length === 0)) return
  emit('set-structure', { type, target, label })
}

/** 移除当前循环实例的结构草稿，并显式收窄操作联合类型。 */
function removePendingStructure(): void {
  const operation = pendingStructureOperation.value
  if (!operation || (operation.type !== 'duplicate_node' && operation.type !== 'delete_node')) return
  emit('remove-structure', operation)
}

/** 判断数组实例 key 是否可用于跨 Runtime 与源码的稳定定位。 */
function isStableInstanceKey(value: unknown): value is string | number {
  return typeof value === 'string'
    || (typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value))
}

/** 将稳定只读原因转换为属性面板提示。 */
function readonlyReasonLabel(reason: string | null | undefined): string {
  const labels: Record<string, string> = {
    SFC_PARSE_ERROR: '页面源码解析失败，此项只读。',
    TEMPLATE_UNSUPPORTED: '当前模板结构暂不支持可视化写回。',
    DYNAMIC_EXPRESSION: '动态表达式仅展示，不支持可视化编辑。',
    DYNAMIC_SCRIPT_SOURCE: '动态脚本数据源仅展示，不支持可视化编辑。',
    SCRIPT_SOURCE_NOT_FOUND: '未找到可安全写回的脚本数据源。',
    LOOP_SOURCE_UNSUPPORTED: '当前循环数据源暂不支持写回。',
    NESTED_LOOP_UNSUPPORTED: '首版不支持嵌套循环实例写回。',
    LOOP_MEMBER_UNSUPPORTED: '循环缺少稳定唯一 key，实例只读。',
    MEMBER_NOT_FOUND: '数组项中未找到对应成员。',
    MEMBER_VALUE_DYNAMIC: '数组成员是动态值，不能安全写回。',
    ATTRIBUTE_VALUE_MISSING: '属性没有可写回的字面量值。',
    RICH_TEXT_DYNAMIC_CONTENT: '段落包含动态表达式，已合并展示但不能安全写回。',
    RICH_TEXT_UNSUPPORTED_STRUCTURE: '段落包含暂无法安全定位的模板控制结构，当前只读。',
    RICH_TEXT_SOURCE_RANGE_UNRESOLVED: '无法定位富文本容器的内部源码范围，该节点已降级为只读。',
  }
  return reason ? labels[reason] ?? `只读：${reason}` : '此项当前只读。'
}
</script>
