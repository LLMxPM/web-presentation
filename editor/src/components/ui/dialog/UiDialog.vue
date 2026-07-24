<!-- 文件功能：基于 Reka UI 封装 Editor 的可访问模态弹窗与尺寸预设。 -->
<template>
  <DialogRoot :open="open" modal @update:open="emit('update:open', $event)">
    <Teleport to="body">
      <div v-if="open" class="dialog-shell fixed inset-0 z-[1000] flex items-center justify-center" :data-dialog-size="resolvedSize" :data-dialog-body-preset="resolvedBodyPreset ?? 'legacy'" :style="{ zIndex }">
      <DialogOverlay as-child><button type="button" class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" :class="overlayClass" :aria-label="title ? `关闭${title}` : '关闭弹窗'" @click="emit('update:open', false)" /></DialogOverlay>
      <DialogContent
        class="dialog-panel fixed z-[1001] flex min-h-0 w-full flex-col overflow-hidden border border-slate-200 bg-white shadow-2xl outline-none"
        :class="panelClass"
        :style="panelStyle"
        @escape-key-down="emit('escape-key-down', $event)"
        @interact-outside="emit('interact-outside', $event)"
        @close-auto-focus="restoreFocus"
      >
        <div v-if="showHeader" class="dialog-header flex shrink-0 items-start justify-between gap-3 border-b border-slate-100 bg-slate-50/50">
          <slot name="header">
            <div class="min-w-0 flex-1">
              <DialogTitle v-if="title" class="line-clamp-1 text-lg font-bold text-slate-900">{{ title }}</DialogTitle>
              <DialogDescription v-if="description" class="mt-1 text-sm leading-6 text-slate-500">{{ description }}</DialogDescription>
            </div>
            <div v-if="$slots['header-extra']" class="flex shrink-0 items-center gap-2"><slot name="header-extra" /></div>
            <DialogClose v-if="showCloseButton" as-child><button type="button" class="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" :aria-label="title ? `关闭${title}` : '关闭弹窗'">×</button></DialogClose>
          </slot>
        </div>
        <div class="dialog-body" :class="[bodyPresetClass, bodyClass]"><slot /></div>
        <div v-if="$slots.footer" class="dialog-footer flex shrink-0 items-center justify-end gap-3 border-t border-slate-100 bg-slate-50/20"><slot name="footer" /></div>
      </DialogContent>
      </div>
    </Teleport>
  </DialogRoot>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, useSlots, watch, type CSSProperties } from 'vue'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogRoot, DialogTitle } from 'reka-ui'

import { DIALOG_BODY_PRESET_CLASS, resolveDialogMaxWidth, resolveDialogTargetHeight, type DialogBodyPreset, type DialogSize } from '../dialog'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  description?: string
  size?: DialogSize
  /** 内容区布局预设；传入 bodyClass 且未显式指定时保留旧组件的完全自定义语义。 */
  bodyPreset?: DialogBodyPreset
  width?: string
  bodyClass?: string
  panelClass?: string
  panelStyle?: CSSProperties
  overlayClass?: string
  showHeader?: boolean
  showCloseButton?: boolean
  zIndex?: number
}>(), { size: 'compact', showHeader: true, showCloseButton: true, zIndex: 1000 })

const emit = defineEmits<{
  'update:open': [value: boolean]
  'escape-key-down': [event: Event]
  'interact-outside': [event: Event]
}>()

const slots = useSlots()
let restoreFocusTarget: HTMLElement | null = null
let focusRestoreTimer: ReturnType<typeof setTimeout> | null = null
const resolvedSize = computed(() => props.size ?? 'compact')
const resolvedBodyPreset = computed<DialogBodyPreset | null>(() => props.bodyPreset ?? (props.bodyClass ? null : 'auto'))
const bodyPresetClass = computed(() => resolvedBodyPreset.value ? DIALOG_BODY_PRESET_CLASS[resolvedBodyPreset.value] : null)
const showHeader = computed(() => props.showHeader && Boolean(slots.header || props.title || props.description || slots['header-extra'] || props.showCloseButton))
const panelStyle = computed<CSSProperties>(() => ({
  width: `min(${resolveDialogMaxWidth(resolvedSize.value, props.width)}, calc(100dvw - (var(--dialog-shell-gap) * 2)))`,
  height: `min(${resolveDialogTargetHeight(resolvedSize.value)}, calc(100dvh - (var(--dialog-shell-gap) * 2)))`,
  maxHeight: 'calc(100dvh - (var(--dialog-shell-gap) * 2))',
  left: '50%', top: '50%', transform: 'translate(-50%, -50%)', borderRadius: 'var(--ui-radius-xl, 12px)',
  ...props.panelStyle,
}))

/**
 * 为受控模式补齐焦点恢复。UiDialog 不强制业务方使用 DialogTrigger，
 * 因此需在打开前记录当前元素，并在关闭后将焦点交还给它。
 */
watch(() => props.open, isOpen => {
  if (isOpen) {
    if (focusRestoreTimer) {
      clearTimeout(focusRestoreTimer)
      focusRestoreTimer = null
    }
    restoreFocusTarget = document.activeElement instanceof HTMLElement ? document.activeElement : null
    return
  }
  if (restoreFocusTarget?.isConnected) {
    focusRestoreTimer = setTimeout(() => restoreFocusTarget?.focus(), 0)
  }
})

/** 阻止 Reka 在无 DialogTrigger 的受控模式中把焦点回退到 body。 */
function restoreFocus(event: Event) {
  if (!restoreFocusTarget?.isConnected) {
    return
  }
  event.preventDefault()
  restoreFocusTarget.focus()
}

onBeforeUnmount(() => {
  if (focusRestoreTimer) {
    clearTimeout(focusRestoreTimer)
  }
})
</script>

<style scoped>
.dialog-shell { --dialog-shell-gap: 24px; padding: var(--dialog-shell-gap); }
.dialog-panel { border-radius: var(--ui-radius-xl, 12px); }
.dialog-header, .dialog-footer { padding: 1rem 1.5rem; }
.dialog-body { min-height: 0; flex: 1 1 auto; }
.dialog-body--auto { overflow-y: auto; padding: 1.25rem 1.5rem; }
.dialog-body--dense, .dialog-body--editor { overflow: hidden; padding: 1.25rem 1.5rem; }
.dialog-body--split, .dialog-body--immersive { overflow: hidden; padding: 0; }
@media (max-height: 820px) { .dialog-shell { --dialog-shell-gap: 16px; } .dialog-panel { border-radius: .75rem; } .dialog-header, .dialog-footer { padding: .75rem 1rem; } .dialog-body--auto, .dialog-body--dense, .dialog-body--editor { padding: 1rem; } }
@media (max-width: 1024px) { .dialog-shell { --dialog-shell-gap: 12px; } }
</style>
