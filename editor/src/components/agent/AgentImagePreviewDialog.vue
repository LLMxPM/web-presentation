<!-- 文件功能：消息流图片的统一沉浸式预览弹窗，提供大图查看、下载与保存为资源能力。 -->
<template>
  <UiDialog
    :open="open"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    :panel-style="{ background: 'transparent' }"
    panel-class="!pointer-events-none !border-0 !bg-transparent !shadow-none"
    overlay-class="bg-overlay/90 backdrop-blur-md"
    :z-index="1200"
    @update:open="handleVisibleChange"
  >
    <div
      v-if="attachment"
      class="pointer-events-none relative flex h-full min-h-0 items-center justify-center p-4 sm:p-6"
    >
      <img
        :src="attachment.url"
        :alt="attachment.original_name"
        class="pointer-events-auto relative max-h-full max-w-full rounded-lg object-contain shadow-2xl drop-shadow-2xl"
      >
      <BaseCloseButton
        class="pointer-events-auto absolute right-3 top-3 sm:right-6 sm:top-6"
        tone="inverse"
        label="关闭图片预览"
        @click="emit('update:open', false)"
      />
      <div class="pointer-events-auto absolute bottom-3 left-1/2 flex max-w-[80%] -translate-x-1/2 items-center gap-1 rounded-full bg-surface-inverse-raised/60 px-2.5 py-1.5 text-xs text-text-inverse backdrop-blur sm:bottom-6">
        <span class="min-w-0 max-w-[10rem] truncate tracking-widest">{{ attachment.original_name }}</span>
        <span class="mx-1 h-3 w-px shrink-0 bg-text-inverse/25" aria-hidden="true" />
        <a
          :href="attachment.url"
          :download="attachment.original_name"
          class="image-preview-action"
          :title="`下载 ${attachment.original_name}`"
          aria-label="下载图片"
        >
          <Download class="h-3.5 w-3.5" />
        </a>
        <button
          v-if="promoteButtonVisible"
          type="button"
          class="image-preview-action"
          :class="{ 'image-preview-action--done': isPromoted }"
          :disabled="promoting || isPromoted"
          :title="promoteButtonTitle"
          :aria-label="promoteButtonTitle"
          @click="handlePromote"
        >
          <Archive class="h-3.5 w-3.5" />
          <span class="whitespace-nowrap">{{ promoteButtonLabel }}</span>
        </button>
      </div>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { Archive, Download } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import { UiDialog } from '@/components/ui'
import type { AgentMessageAttachmentItem } from '@/types/api'

interface Props {
  open: boolean
  attachment: AgentMessageAttachmentItem | null
  /** 保存为资源的执行入口；未提供时隐藏该交互。 */
  promoteAttachment?: ((attachmentId: number) => Promise<boolean>) | null
}

const props = withDefaults(defineProps<Props>(), {
  attachment: null,
  promoteAttachment: null,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const promoting = ref(false)
const locallyPromoted = ref(false)
let lastAttachmentId: number | null = null

watch(
  () => props.attachment?.id ?? null,
  (attachmentId) => {
    if (attachmentId === lastAttachmentId) {
      return
    }
    lastAttachmentId = attachmentId
    locallyPromoted.value = false
    promoting.value = false
  },
  { immediate: true },
)

const isPromoted = computed(() => Boolean(props.attachment?.promoted_asset_id || locallyPromoted.value))
const promoteButtonVisible = computed(() => Boolean(props.promoteAttachment))
const promoteButtonLabel = computed(() => {
  if (isPromoted.value) return '已保存到资源库'
  if (promoting.value) return '保存中...'
  return '保存为资源'
})
const promoteButtonTitle = computed(() => isPromoted.value ? '已保存到资源库' : '保存为资源')

/**
 * 响应遮罩点击与 Esc 关闭，仅向下透传关闭动作。
 */
function handleVisibleChange(visible: boolean) {
  if (!visible) {
    emit('update:open', false)
  }
}

/**
 * 调用父层提供的保存为资源入口；成功后本地回显已保存状态。
 */
async function handlePromote() {
  const attachment = props.attachment
  if (!attachment || isPromoted.value || promoting.value || !props.promoteAttachment) {
    return
  }
  promoting.value = true
  try {
    const succeeded = await props.promoteAttachment(attachment.id)
    if (succeeded) {
      locallyPromoted.value = true
    }
  } finally {
    promoting.value = false
  }
}
</script>

<style scoped>
.image-preview-action {
  display: inline-flex;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  border-radius: 9999px;
  padding: 0 0.375rem;
  color: rgb(var(--ui-text-inverse));
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}

.image-preview-action:hover {
  background: rgb(var(--ui-text-inverse) / 0.14);
}

.image-preview-action:disabled {
  cursor: default;
  opacity: 0.75;
}

.image-preview-action--done {
  color: rgb(var(--ui-success));
}
</style>
