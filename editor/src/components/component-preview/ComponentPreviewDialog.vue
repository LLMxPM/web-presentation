<!-- 文件功能：统一承载组件预览弹窗外壳，供组件库侧栏预览与简化态完整预览复用。 -->
<template>
  <Teleport to="body">
    <Transition name="component-preview-dialog-fade">
      <div v-if="modelValue" class="fixed inset-0 z-[1000] flex items-center justify-center p-4">
        <button
          type="button"
          class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
          :aria-label="closeLabel"
          @click="close"
        />

        <div
          class="relative flex h-[94vh] w-[98vw] flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
          :style="{ maxWidth: width }"
          @click.stop
        >
          <BaseCloseButton
            v-if="showCloseButton"
            class="absolute right-3 top-3 z-20 bg-white/90 shadow-sm ring-1 ring-slate-200 hover:bg-white"
            :label="closeLabel"
            @click="close"
          />
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  width?: string
  closeLabel?: string
  showCloseButton?: boolean
}>(), {
  width: '1520px',
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

<style scoped>
.component-preview-dialog-fade-enter-active,
.component-preview-dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.component-preview-dialog-fade-enter-from,
.component-preview-dialog-fade-leave-to {
  opacity: 0;
}
</style>
