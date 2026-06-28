<!-- 文件功能：封装内容助手输入区，统一处理多行输入、内嵌发送/中断按钮与快捷键提交交互。 -->
<template>
  <section class="shrink-0 border-t border-slate-200 bg-white px-2.5 pb-2 pt-1.5 shadow-[0_-2px_8px_rgba(15,23,42,0.035)]">
    <div
      v-if="!pendingRequirement"
      class="rounded-md border border-slate-200 bg-white px-1.5 py-1 transition focus-within:border-sky-300"
      :class="{ 'opacity-70': composerState === 'disabled' }"
    >
      <textarea
        ref="textareaRef"
        :value="modelValue"
        rows="1"
        class="w-full resize-none bg-transparent px-1 py-0.5 text-[13px] leading-[18px] text-slate-700 outline-none transition-[height]"
        :style="{ height: textareaHeight }"
        :disabled="textareaDisabled"
        :placeholder="placeholder"
        @input="handleInput"
        @keydown.enter.exact.prevent="emitPrimaryAction"
      />

      <div v-if="imageAttachments.length" class="mt-1 flex gap-1.5 overflow-x-auto pb-1">
        <article
          v-for="attachment in imageAttachments"
          :key="attachment.id"
          class="group relative h-14 w-14 shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-50"
        >
          <img
            :src="attachment.url"
            :alt="attachment.original_name"
            class="h-full w-full object-cover"
          >
          <div class="absolute inset-x-1 top-1 flex justify-between gap-1 opacity-0 transition group-hover:opacity-100">
            <button
              type="button"
              class="flex h-4 w-4 items-center justify-center rounded bg-white/90 text-slate-500 shadow-sm hover:text-slate-800"
              aria-label="保存为资源"
              title="保存为资源"
              :disabled="Boolean(attachment.promoted_asset_id)"
              @click="emit('promoteImage', attachment.id)"
            >
              <Archive class="h-2.5 w-2.5" />
            </button>
            <button
              type="button"
              class="flex h-4 w-4 items-center justify-center rounded bg-white/90 text-slate-500 shadow-sm hover:text-red-600"
              aria-label="移除图片"
              title="移除图片"
              @click="emit('removeImage', attachment.id)"
            >
              <X class="h-2.5 w-2.5" />
            </button>
          </div>
        </article>
      </div>

      <div class="mt-0.5 flex items-center justify-between gap-2">
        <div class="flex min-w-0 items-center gap-1">
          <input
            ref="fileInputRef"
            type="file"
            class="hidden"
            accept="image/png,image/jpeg,image/webp"
            multiple
            @change="handleImageInputChange"
          >
          <button
            type="button"
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded transition"
            :class="uploadButtonDisabled ? 'cursor-not-allowed text-slate-300' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'"
            aria-label="上传图片"
            :title="imageUploadDisabledReason || '上传图片'"
            :disabled="uploadButtonDisabled"
            @click="openImagePicker"
          >
            <ImagePlus class="h-3 w-3" />
          </button>
          <button
            type="button"
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
            :aria-label="sizeMode === 'expanded' ? '折叠输入框' : '展开输入框'"
            :aria-pressed="sizeMode === 'expanded'"
            :title="sizeMode === 'expanded' ? '折叠输入框' : '展开输入框'"
            @click="toggleSizeMode"
          >
            <Minimize2 v-if="sizeMode === 'expanded'" class="h-2.5 w-2.5" />
            <Maximize2 v-else class="h-2.5 w-2.5" />
          </button>
          <span v-if="contextUsageVisible" ref="contextUsageRef" class="relative inline-flex shrink-0">
            <button
              type="button"
              class="group flex h-6 w-6 items-center justify-center rounded text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
              :aria-label="contextUsageAriaLabel"
              :aria-expanded="contextUsagePopoverVisible"
              aria-haspopup="dialog"
              @click="toggleContextUsagePopover"
            >
              <svg class="h-3.5 w-3.5 -rotate-90" viewBox="0 0 20 20" aria-hidden="true">
                <circle
                  cx="10"
                  cy="10"
                  r="7"
                  fill="none"
                  stroke="#e2e8f0"
                  stroke-width="3"
                />
                <circle
                  cx="10"
                  cy="10"
                  r="7"
                  fill="none"
                  :stroke="contextUsageColor"
                  stroke-width="3"
                  stroke-linecap="round"
                  :stroke-dasharray="contextUsageDashArray"
                  stroke-dashoffset="0"
                />
              </svg>
            </button>
            <div
              v-if="contextUsagePopoverVisible"
              class="absolute bottom-8 left-0 z-20 w-44 rounded-md border border-slate-200 bg-white p-3 text-xs shadow-lg shadow-slate-900/10"
              role="dialog"
              aria-label="上下文用量详情"
            >
              <div class="flex items-center justify-between gap-3">
                <span class="text-slate-500">已用上下文</span>
                <span class="font-semibold text-slate-800">{{ contextUsedLabel }}</span>
              </div>
              <div class="mt-2 flex items-center justify-between gap-3">
                <span class="text-slate-500">可用上下文</span>
                <span class="font-semibold text-slate-800">{{ contextAvailableLabel }}</span>
              </div>
              <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  class="h-full rounded-full transition-[width]"
                  :class="contextUsageRatio >= 0.9 ? 'bg-red-500' : contextUsageRatio >= 0.7 ? 'bg-amber-500' : 'bg-sky-500'"
                  :style="{ width: `${Math.round(contextUsageRatio * 100)}%` }"
                />
              </div>
            </div>
          </span>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <slot name="action-prefix" />
          <BaseButton
            :variant="primaryActionVariant"
            :loading="composerState === 'interrupting'"
            :disabled="primaryActionDisabled"
            custom-class="h-6 rounded-md px-2 py-0 text-[11px] shadow-none"
            @click="emitPrimaryAction"
          >
            <Square v-if="isRunningState" class="h-2.5 w-2.5" />
            <SendHorizonal v-else class="h-2.5 w-2.5" />
            {{ primaryActionLabel }}
          </BaseButton>
        </div>
      </div>
    </div>
    <AgentToolConfirmPrompt
      v-else-if="pendingRequirement.kind === 'confirmation'"
      :requirement="pendingRequirement"
      :loading="hitlLoading"
      :can-apply-suggested-patch="canApplySuggestedPatch"
      :force-release-available="hitlForceReleaseAvailable"
      @confirm="emit('hitlConfirm')"
      @reject="emit('hitlReject')"
      @force-release="emit('hitlForceRelease')"
      @apply-suggested-patch="patch => emit('applySuggestedPatch', patch)"
      @save-draft-patch="patch => emit('saveDraftPatch', patch)"
    />
    <AgentChoicePrompt
      v-else
      :requirement="pendingRequirement"
      :loading="hitlLoading"
      :force-release-available="hitlForceReleaseAvailable"
      @submit="selections => emit('hitlFeedbackSubmit', selections)"
      @ignore="emit('hitlCancel')"
      @force-release="emit('hitlForceRelease')"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Archive, ImagePlus, Maximize2, Minimize2, SendHorizonal, Square, X } from '@lucide/vue'

import AgentChoicePrompt from '@/components/agent/AgentChoicePrompt.vue'
import AgentToolConfirmPrompt from '@/components/agent/AgentToolConfirmPrompt.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { AgentFeedbackSelection, AgentImageAttachmentItem, AgentPendingRequirement, AgentSuggestedPatch } from '@/types/api'

interface Props {
  modelValue: string
  placeholder: string
  disabled?: boolean
  streaming?: boolean
  interrupting?: boolean
  actionDisabled?: boolean
  contextUsedTokens?: number | null
  contextAvailableTokens?: number | null
  imageAttachments?: AgentImageAttachmentItem[]
  imageUploading?: boolean
  imageUploadDisabled?: boolean
  imageUploadDisabledReason?: string
  pendingRequirement?: AgentPendingRequirement | null
  hitlLoading?: boolean
  canApplySuggestedPatch?: boolean
  hitlForceReleaseAvailable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  streaming: false,
  interrupting: false,
  actionDisabled: false,
  contextUsedTokens: null,
  contextAvailableTokens: null,
  imageAttachments: () => [],
  imageUploading: false,
  imageUploadDisabled: false,
  imageUploadDisabledReason: '',
  pendingRequirement: null,
  hitlLoading: false,
  canApplySuggestedPatch: false,
  hitlForceReleaseAvailable: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  action: []
  uploadImage: [file: File]
  removeImage: [attachmentId: number]
  promoteImage: [attachmentId: number]
  hitlConfirm: []
  hitlReject: []
  hitlCancel: []
  hitlForceRelease: []
  hitlFeedbackSubmit: [selections: AgentFeedbackSelection[]]
  applySuggestedPatch: [patch: AgentSuggestedPatch]
  saveDraftPatch: [patch: AgentSuggestedPatch]
  contextUsageOpen: []
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const contextUsageRef = ref<HTMLElement | null>(null)
const textareaHeight = ref('36px')
const sizeMode = ref<'compact' | 'expanded'>('compact')
const contextUsagePopoverVisible = ref(false)

const TEXTAREA_SIZE_LIMITS = {
  compact: {
    minHeight: 36,
    maxHeight: 104,
  },
  expanded: {
    minHeight: 104,
    maxHeight: 220,
  },
} as const

const activeSizeLimits = computed(() => TEXTAREA_SIZE_LIMITS[sizeMode.value])
const hasInputText = computed(() => props.modelValue.trim().length > 0)
const hasVisualInput = computed(() => hasInputText.value || props.imageAttachments.length > 0)
const composerState = computed<'disabled' | 'interrupting' | 'streaming' | 'ready' | 'empty'>(() => {
  if (props.disabled && !props.streaming) {
    return 'disabled'
  }
  if (props.streaming && props.interrupting) {
    return 'interrupting'
  }
  if (props.streaming) {
    return 'streaming'
  }
  return hasVisualInput.value ? 'ready' : 'empty'
})
const isRunningState = computed(() => composerState.value === 'streaming' || composerState.value === 'interrupting')
const textareaDisabled = computed(() => composerState.value === 'disabled')
const primaryActionLabel = computed(() => (isRunningState.value ? '停止' : '发送'))
const primaryActionVariant = computed(() => (isRunningState.value ? 'secondary' : 'primary'))
const primaryActionDisabled = computed(() => props.actionDisabled || composerState.value === 'disabled')
const uploadButtonDisabled = computed(() => (
  textareaDisabled.value
  || isRunningState.value
  || props.imageUploading
  || props.imageUploadDisabled
))
const contextUsageVisible = computed(() => (
  Number.isFinite(Number(props.contextUsedTokens))
  && Number.isFinite(Number(props.contextAvailableTokens))
  && Number(props.contextAvailableTokens) > 0
))
const contextUsageRatio = computed(() => {
  if (!contextUsageVisible.value) {
    return 0
  }
  return Math.min(1, Math.max(0, Number(props.contextUsedTokens) / Number(props.contextAvailableTokens)))
})
const contextUsageColor = computed(() => (
  contextUsageRatio.value >= 0.9
    ? '#ef4444'
    : contextUsageRatio.value >= 0.7
      ? '#f59e0b'
      : '#0ea5e9'
))
const contextUsageDashArray = computed(() => {
  const circumference = 2 * Math.PI * 7
  const usedLength = Math.max(0, Math.min(circumference, circumference * contextUsageRatio.value))
  return `${usedLength} ${circumference}`
})
const contextUsageAriaLabel = computed(() => '上下文用量')
const contextUsedLabel = computed(() => formatTokenK(props.contextUsedTokens))
const contextAvailableLabel = computed(() => formatTokenK(props.contextAvailableTokens))

watch(() => props.modelValue, () => {
  void nextTick(updateTextareaHeight)
})

watch(sizeMode, () => {
  void nextTick(updateTextareaHeight)
})

watch(contextUsageVisible, (visible) => {
  if (!visible) {
    contextUsagePopoverVisible.value = false
  }
})

onMounted(() => {
  updateTextareaHeight()
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
})

/**
 * 同步文本域输入到父组件，保持面板层状态单一来源。
 * @param event 原生输入事件
 */
function handleInput(event: Event) {
  const target = event.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
  updateTextareaHeight()
}

/**
 * 统一向父层抛出主动作事件，由父层决定当前是发送还是中断。
 */
function emitPrimaryAction() {
  if (primaryActionDisabled.value) {
    return
  }
  emit('action')
}

/**
 * 切换上下文用量浮窗；打开时通知父层按需刷新最新统计。
 */
function toggleContextUsagePopover() {
  contextUsagePopoverVisible.value = !contextUsagePopoverVisible.value
  if (contextUsagePopoverVisible.value) {
    emit('contextUsageOpen')
  }
}

/**
 * 点击上下文用量控件之外的区域时关闭浮窗。
 */
function handleDocumentPointerDown(event: PointerEvent) {
  if (!contextUsagePopoverVisible.value) {
    return
  }
  const target = event.target
  if (target instanceof Node && contextUsageRef.value?.contains(target)) {
    return
  }
  contextUsagePopoverVisible.value = false
}

/**
 * 切换输入框尺寸档位；折叠态限制面板占高，展开态为长提示词提供更多编辑空间。
 */
function toggleSizeMode() {
  sizeMode.value = sizeMode.value === 'expanded' ? 'compact' : 'expanded'
}

/**
 * 打开系统文件选择器，由父层负责上传与错误提示。
 */
function openImagePicker() {
  if (uploadButtonDisabled.value) {
    return
  }
  fileInputRef.value?.click()
}

/**
 * 读取用户选择的图片文件并逐个交给父层处理。
 */
function handleImageInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  for (const file of files) {
    emit('uploadImage', file)
  }
}

/**
 * 根据文本内容和当前折叠状态计算文本域高度，超出最大高度后由文本域内部滚动。
 */
function updateTextareaHeight() {
  const textarea = textareaRef.value
  if (!textarea) {
    return
  }
  const { minHeight, maxHeight } = activeSizeLimits.value

  textarea.style.height = 'auto'
  const nextHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight)
  textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
  textareaHeight.value = `${nextHeight}px`
  textarea.style.height = `${nextHeight}px`
}

/**
 * 将 token 数量换算为向下取整的 K 单位，保持浮窗读数短促稳定。
 */
function formatTokenK(value: number | null | undefined) {
  const normalized = Number(value)
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return '0 K'
  }
  return `${Math.floor(normalized / 1000)} K`
}
</script>
