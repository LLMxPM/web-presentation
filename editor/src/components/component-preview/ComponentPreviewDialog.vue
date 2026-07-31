<!-- 文件功能：统一承载组件预览弹窗外壳，供组件库侧栏预览与简化态完整预览复用。 -->
<template>
  <UiDialog
    :open="modelValue"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    panel-class="bg-surface shadow-xl"
    @update:open="handleOpenChange"
  >
    <div class="relative flex h-full min-h-0 flex-col">
      <BaseCloseButton
        v-if="showCloseButton"
        class="absolute right-3 top-3 z-20 bg-surface/90 shadow-sm ring-1 ring-border hover:bg-surface"
        :label="closeLabel"
        @click="close"
      />
      <slot />
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { UiDialog } from '@/components/ui'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  closeLabel?: string
  showCloseButton?: boolean
}>(), {
  closeLabel: '关闭组件预览',
  showCloseButton: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

/**
 * 将 UiDialog 的受控开关状态转发为组件现有的 v-model 协议。
 */
function handleOpenChange(open: boolean): void {
  emit('update:modelValue', open)
}

/**
 * 关闭预览弹窗并同步 v-model。
 */
function close(): void {
  handleOpenChange(false)
}

void props
</script>
