<!-- 文件功能：统一承载工作空间组件草稿与 Runtime Kit 内建组件的右侧预览工作台。 -->
<template>
  <section class="flex h-full min-h-0 flex-col overflow-hidden bg-slate-50/60">
    <header
      class="flex shrink-0 border-b border-slate-200 bg-white py-2.5"
      :class="simplified ? 'component-preview-header--simplified flex-wrap items-center justify-between gap-2 px-3' : 'items-center justify-between gap-3 px-4'"
    >
      <div :class="simplified ? 'component-preview-header-title min-w-0' : 'min-w-0'">
        <div class="flex flex-wrap items-center gap-2">
          <slot name="title">
            <h3 class="truncate text-sm font-bold text-slate-900">{{ resolvedTitle }}</h3>
          </slot>
          <span v-if="!$slots.title && titleBarComponentCode" class="max-w-[10rem] shrink truncate rounded-full bg-white px-2 py-0.5 text-[10px] font-mono font-bold text-slate-500 ring-1 ring-slate-200">
            {{ titleBarComponentCode }}
          </span>
          <span v-if="source?.kind === 'runtime-kit'" class="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-black text-indigo-600">
            Runtime Kit
          </span>
          <span v-if="source?.kind === 'workspace-draft' && isDraftPreview" class="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-black text-amber-600">
            草稿预览
          </span>
        </div>
        <p v-if="resolvedSubtitle" class="mt-1 truncate text-xs text-slate-400">{{ resolvedSubtitle }}</p>
      </div>

      <div
        class="flex shrink-0 flex-wrap items-center justify-end gap-2"
        :class="simplified ? 'component-preview-header-actions' : ''"
      >
        <div v-if="$slots['component-actions']" class="flex flex-wrap items-center justify-end gap-1.5 border-r border-slate-200 pr-2">
          <slot name="component-actions" :close-full-preview="closeFullPreviewDialog" :inside-full-preview="false" />
        </div>
        <div class="flex items-center justify-end gap-1.5">
          <UiIconButton
            v-if="simplified"
            variant="secondary"
            size="sm"
            :disabled="!source"
            label="弹窗预览"
            @click="openFullPreviewDialog"
          >
            <Maximize2 />
          </UiIconButton>
          <UiIconButton
            variant="secondary"
            size="sm"
            :loading="previewLoading"
            :disabled="!source"
            label="刷新预览"
            @click="refreshCurrentPreview"
          >
            <RefreshCw />
          </UiIconButton>
          <slot name="actions" />
        </div>
      </div>
    </header>

    <DataState
      v-if="!source"
      class="min-h-0 flex-1 p-8"
      state="empty"
      title="请选择左侧组件"
      description="工作空间组件会默认进入预览，Runtime Kit 可预览能力也会显示在这里。"
      :retryable="false"
    />

    <main v-else class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div class="shrink-0 border-b border-slate-200 bg-white">
        <div
          class="component-preview-toolbar-scrollbar-hidden flex min-w-0 gap-2 px-3 py-1.5"
          :class="simplified ? 'flex-wrap items-end overflow-visible' : 'items-center overflow-x-auto'"
        >
          <div v-if="!simplified" class="min-w-max">
            <ComponentPreviewPlacementToolbar
              :model-value="previewConfigDraft"
              embedded
              inline
              @update:model-value="handlePlacementConfigChange"
              @reset-defaults="resetInlinePlacementConfig"
            />
          </div>

          <div v-if="!simplified" class="h-8 w-px shrink-0 bg-slate-200" />

          <div :class="simplified ? 'min-w-0 flex-1' : 'min-w-max'">
            <ComponentPreviewReleaseToolbar
              :model-value="previewConfigDraft"
              :workspace-id="source.workspaceId"
              :preferred-theme-key="workspacePreviewDefaultConfig.page.theme_key"
              :simplified="simplified"
              inline
              @update:model-value="handlePageConfigChange"
            />
          </div>
        </div>

        <ComponentPreviewParameterDock
          :loading="previewLoading"
          :error-message="previewErrorMessage"
          :schema="previewSchema"
          :state="previewState"
          :component-meta="previewComponentMeta"
          :simplified="simplified"
          @update:state="handlePreviewStateChange"
        />
      </div>

      <div class="min-h-0 flex-1 overflow-hidden">
        <div class="relative h-full">
          <DataState
            v-if="!previewFrameUrl"
            class="h-full"
            :state="previewDataState"
            :title="previewStateTitle"
            :description="previewStateDescription"
            @retry="refreshCurrentPreview"
          >
            <template #empty>
              <UiButton size="sm" @click="refreshCurrentPreview">生成预览</UiButton>
            </template>
          </DataState>
          <div
            v-else
            :ref="bindPreviewViewportRef"
            class="relative flex h-full items-center justify-center p-4"
          >
            <div class="relative shrink-0" :style="previewFrameStageStyle">
              <div
                class="absolute left-0 top-0 overflow-hidden rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))] shadow-sm shadow-slate-200/70"
                :style="previewFrameContainerStyle"
              >
                <iframe
                  :ref="bindPreviewFrameRef"
                  :src="previewFrameUrl"
                  :title="iframeTitle"
                  class="block h-full w-full bg-[rgb(var(--ui-surface-muted))]"
                  referrerpolicy="same-origin"
                />
              </div>
            </div>
            <button
              v-if="simplified"
              type="button"
              class="absolute inset-0 z-10 h-full w-full cursor-zoom-in border-0 bg-transparent p-0 opacity-0"
              title="打开完整预览"
              aria-label="打开完整预览"
              @click="openFullPreviewDialog"
            />
          </div>
        </div>
      </div>
    </main>

    <ComponentPreviewDialog v-model="fullPreviewDialogVisible" size="workbench">
      <ComponentPreviewWorkbench
        :source="source"
        :refresh-key="fullPreviewRefreshKey"
        :title="resolvedTitle"
        :subtitle="resolvedSubtitle"
        class="h-full"
      >
        <template v-if="$slots['component-actions']" #component-actions>
          <slot name="component-actions" :close-full-preview="closeFullPreviewDialog" :inside-full-preview="true" />
        </template>
        <template #actions>
          <UiIconButton label="关闭组件预览" @click="closeFullPreviewDialog"><X /></UiIconButton>
        </template>
      </ComponentPreviewWorkbench>
    </ComponentPreviewDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { Maximize2, RefreshCw, X } from '@lucide/vue'

import { getErrorMessage } from '@/api/http'
import { createComponentPreviewArtifactFromSource } from '@/api/preview'
import { createRuntimeKitComponentPreviewArtifact } from '@/api/runtime-kit'
import ComponentPreviewParameterDock from '@/components/component-preview/ComponentPreviewParameterDock.vue'
import ComponentPreviewDialog from '@/components/component-preview/ComponentPreviewDialog.vue'
import ComponentPreviewPlacementToolbar from '@/components/component-preview/ComponentPreviewPlacementToolbar.vue'
import ComponentPreviewReleaseToolbar from '@/components/component-preview/ComponentPreviewReleaseToolbar.vue'
import { DataState } from '@/components/patterns'
import { UiButton, UiIconButton } from '@/components/ui'
import { useComponentPreviewSession } from '@/composables/useComponentPreviewSession'
import { usesZeroPaddingComponentPreview } from '@/composables/useWorkspaceComponentDraft'
import type { ComponentPreviewWorkbenchSource } from '@/components/component-preview/component-preview-workbench'
import type { ComponentPreviewOptions } from '@/types/api'
import {
  cloneComponentPreviewOptions,
  isSamePreviewPageOptions,
  normalizeComponentPreviewOptions,
} from '@/components/component-preview/preview-config'
import { Message } from '@/utils/message'

const props = withDefaults(defineProps<{
  source: ComponentPreviewWorkbenchSource | null
  refreshKey?: number
  title?: string
  subtitle?: string
  simplified?: boolean
}>(), {
  refreshKey: 0,
  title: '',
  subtitle: '',
  simplified: false,
})

const emit = defineEmits<{
  'preview-refreshed': []
}>()

const session = useComponentPreviewSession()
const {
  previewComponentMeta,
  previewConfigDraft,
  previewErrorMessage,
  previewFrameContainerStyle,
  previewFrameStageStyle,
  previewFrameUrl,
  previewLoading,
  previewSchema,
  previewState,
  previewViewportRef,
  workspacePreviewDefaultConfig,
  handlePreviewStateChange,
  previewBaseConfig,
} = session

const AUTO_PREVIEW_REFRESH_DELAY = 500
let autoPreviewRefreshTimer: number | null = null
const fullPreviewDialogVisible = ref(false)
const fullPreviewRefreshKey = ref(0)
const mainPreviewFrameRef = ref<HTMLIFrameElement | null>(null)

const sourceIdentity = computed(() => {
  const source = props.source
  if (!source) return 'empty'
  if (source.kind === 'runtime-kit') {
    return `runtime-kit:${source.item.name}`
  }
  return `workspace:${source.componentId ?? 'new'}`
})

const resolvedTitle = computed(() => {
  if (props.title) return props.title
  const source = props.source
  if (!source) return '组件预览'
  return source.kind === 'runtime-kit' ? source.item.display_name : source.componentName
})

const resolvedSubtitle = computed(() => {
  if (props.subtitle) return props.subtitle
  const source = props.source
  if (!source) return ''
  return source.kind === 'runtime-kit' ? source.item.import_path : ''
})

const titleBarComponentCode = computed(() => previewComponentMeta.value?.code || '')
const isDraftPreview = computed(() => props.source?.kind === 'workspace-draft' && props.source.isDraftPreview)
const iframeTitle = computed(() => props.source?.kind === 'runtime-kit' ? 'runtime-kit-component-preview' : 'component-preview')
const previewDataState = computed<'loading' | 'empty' | 'error' | 'ready'>(() => {
  if (previewLoading.value) return 'loading'
  if (previewErrorMessage.value) return 'error'
  return previewFrameUrl.value ? 'ready' : 'empty'
})
const previewStateTitle = computed(() => {
  if (previewDataState.value === 'loading') return '正在生成组件预览'
  if (previewDataState.value === 'error') return '组件预览生成失败'
  return '当前尚未生成预览'
})
const previewStateDescription = computed(() => {
  if (previewDataState.value === 'loading') return '正在准备页面尺寸、主题与组件参数。'
  if (previewDataState.value === 'error') return previewErrorMessage.value
  return '可以重新生成预览，或检查组件源码和 previewSchema。'
})

watch(
  () => [sourceIdentity.value, props.refreshKey],
  ([identity], oldValue) => {
    const sourceChanged = !oldValue || identity !== oldValue[0]
    if (sourceChanged) {
      void initializeAndRefreshPreview()
      return
    }
    void refreshCurrentPreview()
  },
  { immediate: true },
)

watch(previewFrameUrl, async (frameUrl) => {
  if (!frameUrl) {
    return
  }
  // iframe 地址异步写入后，缩放视口才会由 v-if 挂载；待 DOM 提交后重新量取右侧工作台可用区域。
  await nextTick()
  session.observeViewport()
})

onUnmounted(() => {
  clearAutomaticPageRefresh()
})

/**
 * 初始化当前预览来源的基线配置，并执行首次预览。
 */
async function initializeAndRefreshPreview(): Promise<void> {
  session.resetPreviewState()
  const source = props.source
  if (!source) {
    return
  }
  if (!source.workspaceId) {
    Message.error('缺少工作空间信息，无法生成预览。')
    return
  }

  await session.preparePreviewConfig({
    workspaceId: source.workspaceId,
    baseOptions: source.kind === 'runtime-kit' ? source.item.preview_options : null,
    zeroPaddingPreview: source.kind === 'workspace-draft' && usesZeroPaddingComponentPreview(source.componentType),
  })
  await refreshCurrentPreview()
}

/**
 * 对外暴露刷新能力，供编辑面板保存、预览草稿或应用页面配置后主动触发。
 */
async function refreshCurrentPreview(): Promise<void> {
  clearAutomaticPageRefresh()
  const source = props.source
  if (!source) {
    return
  }
  if (!source.workspaceId) {
    Message.error('缺少工作空间信息，无法生成预览。')
    return
  }

  try {
    await session.runPreview(async () => {
      if (source.kind === 'runtime-kit') {
        return createRuntimeKitComponentPreviewArtifact(source.item.name, {
          workspace_id: source.workspaceId as number,
          preview_options: normalizeComponentPreviewOptions(previewConfigDraft.value),
        })
      }

      const normalizedPreviewSchema = normalizeWorkspacePreviewSchema(source.previewSchema)
      if (!source.content.trim()) {
        throw new Error('组件源码为空，无法生成预览。')
      }
      return createComponentPreviewArtifactFromSource({
        workspace_id: source.workspaceId as number,
        component_id: source.componentId,
        component_name: source.componentName || '未保存组件草稿',
        content: source.content,
        preview_schema: normalizedPreviewSchema,
        preview_options: normalizeComponentPreviewOptions(previewConfigDraft.value),
        file_type: 'vue',
      })
    })
    emit('preview-refreshed')
  } catch (error) {
    const errorMessage = getErrorMessage(error, '生成组件预览失败')
    session.previewLoading.value = false
    session.previewErrorMessage.value = errorMessage
    Message.error(errorMessage)
  }
}

/**
 * 写入组件占位配置；占位仅通过 iframe 消息即时同步，不触发 artifact 重建。
 * @param nextOptions 子控件回传的完整预览配置
 */
function handlePlacementConfigChange(nextOptions: ComponentPreviewOptions): void {
  previewConfigDraft.value = nextOptions
}

/**
 * 写入页面尺寸或主题配置，并在页面配置发生变化时安排自动重建。
 * @param nextOptions 子控件回传的完整预览配置
 */
function handlePageConfigChange(nextOptions: ComponentPreviewOptions): void {
  const pageChanged = !isSamePreviewPageOptions(previewConfigDraft.value.page, nextOptions.page)
  previewConfigDraft.value = nextOptions
  if (pageChanged) {
    scheduleAutomaticPageRefresh()
  }
}

/**
 * 将内联占位控件恢复到当前组件声明的基线占位，不影响页面尺寸与主题。
 */
function resetInlinePlacementConfig(): void {
  const baseOptions = cloneComponentPreviewOptions(previewBaseConfig.value)
  previewConfigDraft.value = {
    ...previewConfigDraft.value,
    placement: baseOptions.placement,
  }
}

/**
 * 页面尺寸和主题变化后延迟重建 artifact，避免连续输入宽高时频繁请求。
 */
function scheduleAutomaticPageRefresh(): void {
  if (!props.source || !previewFrameUrl.value) {
    return
  }
  clearAutomaticPageRefresh()
  autoPreviewRefreshTimer = window.setTimeout(() => {
    autoPreviewRefreshTimer = null
    void refreshCurrentPreview()
  }, AUTO_PREVIEW_REFRESH_DELAY)
}

/**
 * 清理待执行的自动刷新任务。
 */
function clearAutomaticPageRefresh(): void {
  if (!autoPreviewRefreshTimer) {
    return
  }
  window.clearTimeout(autoPreviewRefreshTimer)
  autoPreviewRefreshTimer = null
}

/**
 * 归一化工作空间组件 previewSchema 文本，预览链路只接受 JSON 对象或空值。
 * @param rawValue 原始 previewSchema 文本
 */
function normalizeWorkspacePreviewSchema(rawValue: string | null): string | null {
  const normalizedValue = String(rawValue || '').trim()
  if (!normalizedValue) {
    return null
  }
  const parsedValue = JSON.parse(normalizedValue)
  if (!parsedValue || Array.isArray(parsedValue) || typeof parsedValue !== 'object') {
    throw new Error('previewSchema 必须是 JSON 对象。')
  }
  return JSON.stringify(parsedValue, null, 2)
}

/**
 * 绑定预览缩放容器引用，供 ResizeObserver 计算 contain 缩放。
 * @param element 预览容器元素
 */
function bindPreviewViewportRef(element: Element | ComponentPublicInstance | null): void {
  previewViewportRef.value = element instanceof HTMLElement ? element : null
  session.observeViewport()
}

/**
 * 绑定 iframe 引用，供 postMessage 调参协议使用。
 * @param element iframe 元素
 */
function bindPreviewFrameRef(element: Element | ComponentPublicInstance | null): void {
  mainPreviewFrameRef.value = element instanceof HTMLIFrameElement ? element : null
  if (!fullPreviewDialogVisible.value) {
    session.previewFrameRef.value = mainPreviewFrameRef.value
  }
}

/**
 * 打开完整态预览弹窗。
 */
function openFullPreviewDialog(): void {
  fullPreviewRefreshKey.value += 1
  fullPreviewDialogVisible.value = true
}

/**
 * 关闭完整态预览弹窗。
 */
function closeFullPreviewDialog(): void {
  fullPreviewDialogVisible.value = false
}

defineExpose({
  refreshCurrentPreview,
})
</script>

<style scoped>
.component-preview-header--simplified {
  container-type: inline-size;
}

.component-preview-header-title {
  flex: 1 1 14rem;
}

.component-preview-header-actions {
  flex: 0 0 auto;
}

@container (max-width: 560px) {
  .component-preview-header-title {
    flex-basis: 100%;
    width: 100%;
  }

  .component-preview-header-actions {
    flex-basis: 100%;
    width: 100%;
  }
}

@container (max-width: 320px) {
  .component-preview-header-title :deep(.component-preview-title-code) {
    display: none;
  }
}

.component-preview-toolbar-scrollbar-hidden {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.component-preview-toolbar-scrollbar-hidden::-webkit-scrollbar {
  display: none;
}
</style>

