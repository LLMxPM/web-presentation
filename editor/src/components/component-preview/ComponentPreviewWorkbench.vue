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
          <button
            v-if="simplified"
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-not-allowed disabled:border-slate-100 disabled:bg-slate-50 disabled:text-slate-300"
            :disabled="!source"
            title="弹窗预览"
            aria-label="弹窗预览"
            @click="openFullPreviewDialog"
          >
            <Maximize2 class="h-4 w-4" />
          </button>
          <button
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-not-allowed disabled:border-slate-100 disabled:bg-slate-50 disabled:text-slate-300"
            :loading="previewLoading"
            :disabled="!source"
            title="刷新预览"
            aria-label="刷新预览"
            @click="refreshCurrentPreview"
          >
            <RefreshCw class="h-4 w-4" :class="previewLoading ? 'animate-spin' : ''" />
          </button>
          <slot name="actions" />
        </div>
      </div>
    </header>

    <div v-if="!source" class="flex min-h-0 flex-1 items-center justify-center p-8">
      <div class="max-w-sm rounded-xl border border-dashed border-slate-200 bg-white px-7 py-8 text-center">
        <PackageOpen class="mx-auto mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-bold text-slate-600">请选择左侧组件</p>
        <p class="mt-2 text-xs leading-6 text-slate-400">工作空间组件会默认进入预览，Runtime Kit 可预览能力也会显示在这里。</p>
      </div>
    </div>

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
        <div
          :ref="bindPreviewViewportRef"
          class="relative flex h-full items-center justify-center"
          :class="simplified ? 'p-2' : 'p-4'"
        >
          <div class="relative shrink-0" :style="previewFrameStageStyle">
            <div
              class="absolute left-0 top-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm shadow-slate-200/70"
              :style="previewFrameContainerStyle"
            >
              <iframe
                v-if="previewFrameUrl"
                :ref="bindPreviewFrameRef"
                :src="previewFrameUrl"
                :title="iframeTitle"
                class="block h-full w-full bg-slate-50"
                referrerpolicy="same-origin"
              />
              <div
                v-else
                class="flex h-full items-center justify-center px-6 text-center text-sm leading-7 text-slate-400"
              >
                {{ previewPlaceholderText }}
              </div>
            </div>
          </div>
          <button
            v-if="simplified && previewFrameUrl"
            type="button"
            class="absolute inset-0 z-10 cursor-zoom-in bg-transparent"
            title="打开完整预览"
            aria-label="打开完整预览"
            @click="openFullPreviewDialog"
          />
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
          <BaseCloseButton label="关闭组件预览" @click="closeFullPreviewDialog" />
        </template>
      </ComponentPreviewWorkbench>
    </ComponentPreviewDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { Maximize2, PackageOpen, RefreshCw } from '@lucide/vue'

import { getErrorMessage } from '@/api/http'
import { createComponentPreviewArtifactFromSource } from '@/api/preview'
import { createRuntimeKitComponentPreviewArtifact } from '@/api/runtime-kit'
import ComponentPreviewParameterDock from '@/components/component-preview/ComponentPreviewParameterDock.vue'
import ComponentPreviewDialog from '@/components/component-preview/ComponentPreviewDialog.vue'
import ComponentPreviewPlacementToolbar from '@/components/component-preview/ComponentPreviewPlacementToolbar.vue'
import ComponentPreviewReleaseToolbar from '@/components/component-preview/ComponentPreviewReleaseToolbar.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
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
const previewPlaceholderText = computed(() => (
  previewLoading.value ? '正在生成组件预览...' : '当前尚未生成预览，请点击“刷新预览”。'
))

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

