<!-- 文件功能：组织页面可视化编辑三栏工作区，管理 artifact 分析、非实时草稿、保存刷新与诊断展示。 -->
<template>
  <section class="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
    <header v-if="props.showHeader" class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2.5">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <h2 class="truncate text-sm font-bold text-slate-800">可视化编辑 · {{ props.pageTitle }}</h2>
          <span
            v-if="session.pendingCount.value"
            class="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-bold text-indigo-700"
          >
            {{ session.pendingCount.value }} 项待保存
          </span>
          <span v-if="session.stale.value" class="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">
            已过期
          </span>
        </div>
        <p class="mt-0.5 text-xs text-slate-500">编辑期间画布保持当前 artifact；保存成功后重新分析并刷新。</p>
      </div>

      <div class="flex items-center gap-2">
        <BaseButton
          variant="ghost"
          size="sm"
          :disabled="busy || !session.hasPendingChanges.value"
          @click="discardChanges"
        >
          <Undo2 class="h-3.5 w-3.5" />
          放弃修改
        </BaseButton>
        <BaseButton variant="ghost" size="sm" :disabled="busy" @click="reanalyze">
          <RefreshCw class="h-3.5 w-3.5" />
          重新分析
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          :loading="session.saving.value"
          :disabled="busy || !session.hasPendingChanges.value || session.stale.value"
          @click="saveChanges"
        >
          <Save class="h-3.5 w-3.5" />
          保存并刷新
        </BaseButton>
      </div>
    </header>

    <div
      v-if="session.errorMessage.value"
      role="alert"
      class="shrink-0 border-b border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-700"
    >
      {{ session.errorMessage.value }}
    </div>
    <div
      v-if="diagnostics.length"
      class="max-h-24 shrink-0 overflow-auto border-b border-amber-200 bg-amber-50 px-4 py-2"
    >
      <p
        v-for="diagnostic in diagnostics"
        :key="`${diagnostic.code}:${diagnostic.source_range?.start ?? ''}:${diagnostic.source_range?.end ?? ''}:${diagnostic.message}`"
        class="text-xs text-amber-800"
      >
        <span class="font-bold">{{ diagnostic.code }}</span> · {{ diagnostic.message }}
      </p>
    </div>

    <div class="grid min-h-0 flex-1 grid-cols-[15rem_minmax(20rem,1fr)_21rem] overflow-hidden">
      <PageVisualEditLayerTree
        :root="session.manifest.value?.root ?? null"
        :selected-node-id="session.selectedNodeId.value"
        @select="handleLayerSelect"
      />

      <main class="relative min-h-0 overflow-hidden bg-slate-200 p-3">
        <div v-if="session.loading.value" class="absolute inset-0 z-10 flex items-center justify-center bg-white/80">
          <div class="flex items-center gap-2 text-sm font-semibold text-slate-600">
            <LoaderCircle class="h-5 w-5 animate-spin text-indigo-600" />
            正在分析 Vue 页面…
          </div>
        </div>

        <div v-if="session.artifact.value" class="h-full overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm">
          <iframe
            ref="previewFrame"
            :src="session.artifact.value.preview_url"
            :title="`${props.pageTitle} 可视化编辑画布`"
            class="h-full w-full border-0 bg-white"
          />
        </div>
        <div v-else class="flex h-full items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white text-sm text-slate-400">
          {{ session.errorMessage.value || '等待创建编辑态 artifact。' }}
        </div>

        <div class="pointer-events-none absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full bg-slate-900/85 px-3 py-1.5 text-[11px] font-semibold text-white shadow-lg">
          属性修改不会实时覆盖画布 · 保存后刷新
        </div>
      </main>

      <PageVisualEditPropertyInspector
        :node="session.selectedNode.value"
        :selected-binding-id="session.selectedBindingId.value"
        :selected-instance-path="session.selectedInstancePath.value"
        :loop-node-id="selectedLoopNodeId"
        :catalog="session.manifest.value?.tailwind_catalog ?? null"
        :component-schemas="session.artifact.value?.visual_edit.component_schemas ?? {}"
        :pending-operations="session.pendingOperations.value"
        @select-binding="handleBindingSelect"
        @set-value="session.setValue($event.target, $event.value, $event.baselineValue)"
        @set-tailwind="session.setTailwindTokens($event.target, $event.changes, $event.baselineChanges)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { LoaderCircle, RefreshCw, Save, Undo2 } from '@lucide/vue'

import PageVisualEditLayerTree from '@/components/page-detail/visual-edit/PageVisualEditLayerTree.vue'
import PageVisualEditPropertyInspector from '@/components/page-detail/visual-edit/PageVisualEditPropertyInspector.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { usePageVisualEditSession } from '@/composables/usePageVisualEditSession'
import type {
  PageVisualEditApplyResponse,
  PageVisualEditNode,
  PageVisualEditPanelState,
} from '@/types/page-visual-edit'
import { createConfirm, Message } from '@/utils/message'

const props = withDefaults(defineProps<{
  pageId: number
  baseVersionNo: number
  pageTitle: string
  showHeader?: boolean
}>(), {
  showHeader: true,
})

const emit = defineEmits<{
  saved: [response: PageVisualEditApplyResponse]
  'dirty-change': [dirty: boolean]
  'busy-change': [busy: boolean]
  'state-change': [state: PageVisualEditPanelState]
}>()

const session = usePageVisualEditSession()
const previewFrame = ref<HTMLIFrameElement | null>(null)
const busy = computed(() => session.loading.value || session.saving.value)
const diagnostics = computed(() => {
  const items = [
    ...(session.artifact.value?.visual_edit.warnings ?? []),
    ...(session.manifest.value?.diagnostics ?? []),
  ]
  return items.filter((item, index) => (
    items.findIndex(candidate => (
      candidate.code === item.code
      && candidate.message === item.message
      && candidate.source_range?.start === item.source_range?.start
      && candidate.source_range?.end === item.source_range?.end
    )) === index
  ))
})
const selectedLoopNodeId = computed(() => {
  const root = session.manifest.value?.root
  return root ? findNearestLoopNodeId(root, session.selectedNodeId.value) : ''
})

watch(previewFrame, frame => { session.previewFrameRef.value = frame })
watch(session.hasPendingChanges, dirty => emit('dirty-change', dirty), { immediate: true })
watch(busy, pending => emit('busy-change', pending), { immediate: true })
watch(
  [session.pendingCount, session.hasPendingChanges, session.stale, session.saving],
  ([pendingCount, hasPendingChanges, stale, saving]) => emit('state-change', {
    pendingCount,
    hasPendingChanges,
    stale,
    saving,
  }),
  { immediate: true },
)

watch(
  () => [props.pageId, props.baseVersionNo] as const,
  ([nextPageId, nextVersionNo], previous) => {
    if (!previous || (nextPageId === previous[0] && nextVersionNo === previous[1])) return
    if (
      session.artifact.value?.visual_edit.page_id === nextPageId
      && session.artifact.value.visual_edit.base_version_no === nextVersionNo
    ) return
    if (session.hasPendingChanges.value) {
      session.markStale()
      return
    }
    session.reset()
    void session.analyze(nextPageId, nextVersionNo)
  },
)

onMounted(() => {
  void session.analyze(props.pageId, props.baseVersionNo)
})

/** 从图层树选择节点，模板级选择默认不携带运行实例。 */
function handleLayerSelect(node: PageVisualEditNode): void {
  session.selectNode(node.node_id)
}

/** 在当前节点内切换属性，同时保留来自 Runtime 的循环实例上下文。 */
function handleBindingSelect(bindingId: string): void {
  const nodeId = session.selectedNodeId.value
  if (!nodeId) return
  session.selectNode(nodeId, bindingId, session.selectedInstancePath.value)
}

/** 放弃全部本地操作；此动作不会重新生成 artifact。 */
function discardChanges(): void {
  session.discardChanges()
  Message.info('已放弃可视化编辑草稿。')
}

/** 重新分析最新版本；存在草稿时先明确确认放弃。 */
async function reanalyze(): Promise<void> {
  if (session.hasPendingChanges.value) {
    const confirmed = await createConfirm('重新分析会放弃当前可视化编辑草稿，是否继续？', '重新分析页面')
    if (!confirmed) return
  }
  session.reset()
  await session.analyze(props.pageId, props.baseVersionNo)
}

/** 批量提交草稿；apply 失败保留草稿，成功后通知页面详情刷新规范版本。 */
async function saveChanges(): Promise<void> {
  const result = await session.save(props.pageId)
  if (!result) return
  emit('saved', result)
  if (session.lastRefreshSucceeded.value) {
    Message.success(`已保存 ${result.operations_applied} 项可视化修改，并刷新编辑画布。`)
  } else {
    Message.warning('修改已保存，但编辑画布重新分析失败，请稍后重试。')
  }
}

/** 沿节点路径查找距离目标最近的循环节点，供 script-array 实例定位。 */
function findNearestLoopNodeId(root: PageVisualEditNode, targetNodeId: string, inherited = ''): string {
  const current = root.loop_context?.loop_node_id ?? inherited
  if (root.node_id === targetNodeId) return current
  for (const child of root.children) {
    const found = findNearestLoopNodeId(child, targetNodeId, current)
    if (found) return found
  }
  return ''
}

defineExpose({
  discardChanges,
  reanalyze,
  markStale: session.markStale,
  saveChanges,
})
</script>
