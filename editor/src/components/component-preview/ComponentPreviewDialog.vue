<!-- 文件功能：统一承载组件预览弹窗外壳，供组件库侧栏预览与简化态完整预览复用。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    panel-class="bg-white shadow-xl"
    @update:model-value="close"
  >
    <div class="relative flex h-full min-h-0 flex-col">
      <BaseCloseButton
        v-if="showCloseButton"
        class="absolute right-3 top-3 z-20 bg-white/90 shadow-sm ring-1 ring-slate-200 hover:bg-white"
        :label="closeLabel"
        @click="close"
      />
      <slot />
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import BaseDialog from '@/components/ui/BaseDialog.vue'
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
 * 关闭预览弹窗并同步 v-model。
 */
function close(): void {
  emit('update:modelValue', false)
}

void props
</script>
