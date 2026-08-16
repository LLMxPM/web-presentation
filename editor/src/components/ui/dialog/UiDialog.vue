<!-- 文件功能：基于 Reka UI 封装 Editor 的可访问模态弹窗与尺寸预设。 -->
<template>
  <DialogRoot :open="open" modal @update:open="emit('update:open', $event)">
    <Teleport to="body">
      <div v-if="open" class="dialog-shell fixed inset-0 z-dialog flex items-center justify-center" :data-dialog-size="resolvedSize" :data-dialog-body-preset="resolvedBodyPreset ?? 'legacy'" :style="{ zIndex }">
      <DialogOverlay as-child><button type="button" :class="overlayButtonClass" :aria-label="title ? `关闭${title}` : '关闭弹窗'" @click="emit('update:open', false)" /></DialogOverlay>
      <DialogContent
        v-bind="dialogContentA11yAttrs"
        class="dialog-panel fixed z-[1001] flex min-h-0 w-full flex-col overflow-hidden border border-border bg-surface shadow-2xl outline-none"
        :class="panelClass"
        :style="panelStyle"
        @escape-key-down="emit('escape-key-down', $event)"
        @interact-outside="handleInteractOutside"
        @close-auto-focus="restoreFocus"
      >
        <DialogTitle v-if="!showHeader && title" class="sr-only">{{ title }}</DialogTitle>
        <div v-if="showHeader" class="dialog-header flex shrink-0 items-start justify-between gap-3 border-b border-border-muted bg-canvas/50">
          <slot name="header">
            <div class="min-w-0 flex-1">
              <DialogTitle v-if="title" class="line-clamp-1 text-lg font-bold text-text-strong">{{ title }}</DialogTitle>
              <DialogDescription v-if="description" class="mt-1 text-sm leading-6 text-text-muted">{{ description }}</DialogDescription>
            </div>
            <div v-if="$slots['header-extra']" class="flex shrink-0 items-center gap-2"><slot name="header-extra" /></div>
            <BaseCloseButton v-if="showCloseButton" :label="title ? `关闭${title}` : '关闭弹窗'" @click="emit('update:open', false)" />
          </slot>
        </div>
        <div class="dialog-body" :class="[bodyPresetClass, bodyClass]"><slot /></div>
        <div v-if="$slots.footer" class="dialog-footer flex shrink-0 items-center justify-end gap-3 border-t border-border-muted bg-canvas/20"><slot name="footer" /></div>
      </DialogContent>
      </div>
    </Teleport>
  </DialogRoot>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, useSlots, watch, type CSSProperties } from 'vue'
import { DialogContent, DialogDescription, DialogOverlay, DialogRoot, DialogTitle } from 'reka-ui'

import BaseCloseButton from '../BaseCloseButton.vue'
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
  /** 是否隐藏蒙版底色与模糊，用于侧栏抽屉等需要透出下层内容的弹层。 */
  bareOverlay?: boolean
  showHeader?: boolean
  showCloseButton?: boolean
  zIndex?: string | number
}>(), { size: 'compact', showHeader: true, showCloseButton: true, zIndex: 1000, bareOverlay: false })

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
/**
 * 当业务明确不提供描述时，覆盖 Reka UI 自动生成的描述关联，避免无意义的警告。
 * 有描述时返回空对象，保留 Reka UI 对 DialogDescription 的默认关联。
 */
const dialogContentA11yAttrs = computed<Record<string, undefined>>(() => (
  props.description ? {} : { 'aria-describedby': undefined }
))
const showHeader = computed(() => props.showHeader && Boolean(slots.header || props.title || props.description || slots['header-extra'] || props.showCloseButton))
const overlayButtonClass = computed(() => [
  'absolute inset-0',
  props.bareOverlay ? null : 'bg-overlay/40 backdrop-blur-sm',
  props.overlayClass,
])
const panelStyle = computed<CSSProperties>(() => ({
  width: `min(${resolveDialogMaxWidth(resolvedSize.value, props.width)}, calc(100dvw - (var(--dialog-shell-gap) * 2)))`,
  height: `min(${resolveDialogTargetHeight(resolvedSize.value)}, calc(100dvh - (var(--dialog-shell-gap) * 2)))`,
  maxHeight: 'calc(100dvh - (var(--dialog-shell-gap) * 2))',
  left: '50%', top: '50%', transform: 'translate(-50%, -50%)', borderRadius: 'var(--ui-radius-xl, 12px)',
  ...props.panelStyle,
}))

/**
 * 全局浮层入口位于 DialogContent 外部，但点击它不应关闭当前弹窗。
 * @param event Reka 包装的外部交互事件
 */
function handleInteractOutside(event: Event): void {
  const originalEvent = (event as CustomEvent<{ originalEvent?: Event }>).detail?.originalEvent
  const target = originalEvent?.target ?? event.target
  if (target instanceof Element && target.closest('[data-dialog-overlay-trigger]')) {
    event.preventDefault()
  }
  emit('interact-outside', event)
}

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
