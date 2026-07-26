<!-- 文件功能：在主应用模态层中统一渲染全局确认请求，支持嵌套弹窗与焦点恢复。 -->
<template>
  <UiDialog
    :open="Boolean(activeConfirmRequest)"
    :title="activeConfirmRequest?.title"
    size="compact"
    z-index="var(--ui-z-confirm-overlay)"
    :panel-style="{ height: 'auto' }"
    @update:open="handleVisibleChange"
  >
    <p class="text-sm leading-6 text-text-secondary">{{ activeConfirmRequest?.message }}</p>

    <template #footer>
      <UiButton variant="ghost" size="sm" @click="resolveActiveConfirm(false)">
        {{ activeConfirmRequest?.cancelLabel }}
      </UiButton>
      <UiButton
        :variant="activeConfirmRequest?.dangerous ? 'danger' : 'primary'"
        size="sm"
        @click="resolveActiveConfirm(true)"
      >
        {{ activeConfirmRequest?.confirmLabel }}
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount } from 'vue'

import UiButton from '@/components/ui/button/UiButton.vue'
import UiDialog from '@/components/ui/dialog/UiDialog.vue'
import {
  activeConfirmRequest,
  cancelAllConfirmRequests,
  resolveActiveConfirm,
} from '@/utils/confirm'

/**
 * 将遮罩、关闭按钮与 Esc 产生的关闭事件统一解释为取消。
 */
function handleVisibleChange(visible: boolean): void {
  if (!visible) resolveActiveConfirm(false)
}

onBeforeUnmount(cancelAllConfirmRequests)
</script>
