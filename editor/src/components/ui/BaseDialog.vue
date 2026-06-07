<!-- 文件功能：基础弹窗组件，承载表单或确认信息。 -->
<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="modelValue"
        class="dialog-shell fixed inset-0 flex items-center justify-center"
        :data-dialog-size="resolvedSize"
        :data-dialog-body-preset="resolvedBodyPreset ?? 'legacy'"
        :style="{ zIndex: props.zIndex ?? 1000 }"
      >
        <button
          type="button"
          class="absolute inset-0"
          :class="props.overlayClass || 'bg-slate-900/40 backdrop-blur-sm'"
          :aria-label="props.title ? `关闭${props.title}` : '关闭弹窗'"
          @click="close"
        />

        <Transition name="scale">
          <div
            v-if="modelValue"
            class="dialog-panel relative flex w-full min-h-0 flex-col overflow-hidden border border-slate-200 bg-white shadow-2xl"
            :class="props.panelClass"
            :style="resolvedPanelStyle"
            @click.stop
          >
            <div v-if="showResolvedHeader" class="dialog-header flex shrink-0 items-start justify-between gap-3 border-b border-slate-100 bg-slate-50/50">
              <slot name="header">
                <div class="min-w-0 flex-1">
                  <h3 v-if="title" class="line-clamp-1 text-lg font-bold text-slate-900">{{ title }}</h3>
                  <p v-if="description" class="mt-1 text-sm leading-6 text-slate-500">{{ description }}</p>
                </div>

                <div v-if="$slots['header-extra']" class="flex shrink-0 items-center gap-2">
                  <slot name="header-extra" />
                </div>

                <BaseCloseButton
                  v-if="showCloseButton"
                  class="shrink-0"
                  :label="title ? `关闭${title}` : '关闭弹窗'"
                  @click="close"
                />
              </slot>
            </div>

            <div
              class="dialog-body"
              :class="[resolvedBodyPresetClass, props.bodyClass]"
            >
              <slot></slot>
            </div>

            <div v-if="$slots.footer" class="dialog-footer flex shrink-0 items-center justify-end gap-3 border-t border-slate-100 bg-slate-50/20">
              <slot name="footer"></slot>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, useSlots, type CSSProperties } from 'vue'

import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import {
  DIALOG_BODY_PRESET_CLASS,
  resolveDialogMaxWidth,
  resolveDialogTargetHeight,
  type DialogBodyPreset,
  type DialogSize,
} from '@/components/ui/dialog'

/**
 * 基础弹窗组件，统一承载 Editor 内的模态对话框与沉浸式预览容器。
 */
const props = withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  description?: string
  size?: DialogSize
  bodyPreset?: DialogBodyPreset
  width?: string
  bodyClass?: string
  panelClass?: string
  panelStyle?: CSSProperties
  overlayClass?: string
  showHeader?: boolean
  showCloseButton?: boolean
  zIndex?: number
}>(), {
  size: 'compact',
  showHeader: true,
  showCloseButton: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()
const slots = useSlots()

const resolvedSize = computed(() => props.size ?? 'compact')
const resolvedBodyPreset = computed<DialogBodyPreset | null>(() => props.bodyPreset ?? (props.bodyClass ? null : 'auto'))
const resolvedBodyPresetClass = computed(() => (
  resolvedBodyPreset.value ? DIALOG_BODY_PRESET_CLASS[resolvedBodyPreset.value] : null
))
const showResolvedHeader = computed(() => (
  props.showHeader
  && (
    Boolean(slots.header)
    || Boolean(props.title)
    || Boolean(props.description)
    || Boolean(slots['header-extra'])
    || props.showCloseButton
  )
))
const resolvedPanelStyle = computed<CSSProperties>(() => ({
  '--dialog-max-width': resolveDialogMaxWidth(resolvedSize.value, props.width),
  '--dialog-target-height': resolveDialogTargetHeight(resolvedSize.value),
  ...props.panelStyle,
}) as CSSProperties)

/**
 * 关闭弹窗并向外同步 v-model。
 */
function close() {
  emit('update:modelValue', false)
}

/**
 * 监听 Esc 快捷键，允许用户在任意弹窗层级快速关闭当前模态。
 * @param event 键盘事件
 */
function handleEsc(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.modelValue) {
    close()
  }
}

onMounted(() => window.addEventListener('keydown', handleEsc))
onUnmounted(() => window.removeEventListener('keydown', handleEsc))
</script>

<style scoped>
.dialog-shell {
  --dialog-shell-gap: 24px;
  padding: var(--dialog-shell-gap);
}

.dialog-panel {
  width: min(var(--dialog-max-width), calc(100dvw - (var(--dialog-shell-gap) * 2)));
  height: min(var(--dialog-target-height), calc(100dvh - (var(--dialog-shell-gap) * 2)));
  max-height: calc(100dvh - (var(--dialog-shell-gap) * 2));
  border-radius: 1rem;
}

.dialog-header,
.dialog-footer {
  padding: 1rem 1.5rem;
}

.dialog-body {
  min-height: 0;
  flex: 1 1 auto;
}

.dialog-body--auto {
  overflow-y: auto;
  padding: 1.25rem 1.5rem;
}

.dialog-body--dense {
  overflow: hidden;
  padding: 1.25rem 1.5rem;
}

.dialog-body--editor {
  overflow: hidden;
  padding: 1.25rem 1.5rem;
}

.dialog-body--split {
  overflow: hidden;
  padding: 0;
}

.dialog-body--immersive {
  overflow: hidden;
  padding: 0;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

.scale-enter-active, .scale-leave-active {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.scale-enter-from, .scale-leave-to {
  transform: scale(0.9) translateY(10px);
  opacity: 0;
}

@media (max-height: 820px) {
  .dialog-shell {
    --dialog-shell-gap: 16px;
  }

  .dialog-panel {
    border-radius: 0.75rem;
  }

  .dialog-header,
  .dialog-footer {
    padding: 0.75rem 1rem;
  }

  .dialog-body--auto,
  .dialog-body--dense,
  .dialog-body--editor {
    padding: 1rem;
  }
}

@media (max-width: 1024px) {
  .dialog-shell {
    --dialog-shell-gap: 12px;
  }
}
</style>
