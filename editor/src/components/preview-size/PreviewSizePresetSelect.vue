<!-- 文件功能：提供用户级预设尺寸的下拉选择与维护入口，可在各类页面尺寸配置位置复用。 -->
<template>
  <div ref="rootRef" class="relative w-full" :class="embedded ? 'h-full' : ''">
    <label v-if="label" class="mb-1.5 ml-1 block text-base font-semibold text-slate-700">{{ label }}</label>
    <button
      ref="triggerRef"
      type="button"
      class="flex w-full items-center justify-between gap-2 text-left transition"
      :class="[
        compact ? 'h-9 px-3 text-xs' : 'h-10 px-3 text-sm',
        embedded
          ? 'h-full rounded-none border-0 bg-transparent hover:bg-slate-50'
          : 'rounded-xl border border-slate-200 bg-white hover:border-slate-300',
      ]"
      :disabled="disabled"
      @click="toggleDropdown"
    >
      <span class="min-w-0">
        <span class="block truncate font-semibold text-slate-700">{{ selectedLabel }}</span>
        <span v-if="!compact" class="block truncate text-[11px] text-slate-400">{{ currentWidth }} × {{ currentHeight }}</span>
      </span>
      <ChevronDown class="h-4 w-4 shrink-0 text-slate-400 transition" :class="open ? 'rotate-180' : ''" />
    </button>

    <Teleport to="body">
      <Transition name="preset-fade">
        <div
          v-if="open"
          ref="dropdownRef"
          class="fixed z-[1700] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
          :style="dropdownStyle"
        >
          <div class="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <div class="text-sm font-bold text-slate-800">我的尺寸模板</div>
            </div>
            <button
              type="button"
              class="inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-indigo-600 transition hover:bg-indigo-50"
              @click="startCreatePreset"
            >
              <Plus class="h-3.5 w-3.5" />
              新增
            </button>
          </div>

          <div class="max-h-[240px] overflow-y-auto py-1">
            <div v-if="draftPresets.length === 0" class="px-4 py-8 text-center text-sm text-slate-400">
              暂无预设，可新增后保存。
            </div>

            <div
              v-for="(preset, index) in draftPresets"
              :key="buildPreviewSizePresetKey(preset, index)"
              class="group flex items-center gap-2 px-3 py-2 transition hover:bg-slate-50"
              :class="isPresetSelected(preset) ? 'bg-indigo-50' : ''"
            >
              <button type="button" class="min-w-0 flex-1 text-left" @click="applyPreset(preset)">
                <span class="block truncate text-sm font-semibold" :class="isPresetSelected(preset) ? 'text-indigo-700' : 'text-slate-700'">
                  {{ preset.name }}
                </span>
                <span class="block text-[11px]" :class="isPresetSelected(preset) ? 'text-indigo-500' : 'text-slate-400'">
                  {{ resolvePresetSummary(preset) }}
                </span>
              </button>
              <button
                type="button"
                class="rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-indigo-600"
                title="编辑"
                @click="startEditPreset(index)"
              >
                <Pencil class="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                class="rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-rose-600"
                title="删除"
                @click="deleteDraftPreset(index)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div v-if="formVisible" class="border-t border-slate-100 bg-slate-50/70 p-3">
            <div class="grid grid-cols-[minmax(0,1.2fr)_84px_84px] gap-2">
              <input
                v-model="presetForm.name"
                type="text"
                placeholder="名称"
                class="h-9 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-indigo-500"
              >
              <input
                v-model="presetForm.width"
                type="text"
                inputmode="numeric"
                placeholder="宽"
                class="h-9 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-indigo-500"
              >
              <input
                v-model="presetForm.height"
                type="text"
                inputmode="numeric"
                placeholder="高"
                class="h-9 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-indigo-500"
              >
            </div>
            <div class="mt-2 grid grid-cols-2 gap-2">
              <input
                v-model="presetForm.baseFontSize"
                type="text"
                placeholder="字号"
                class="h-9 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-indigo-500"
              >
              <input
                v-model="presetForm.iconDefaultStrokeWidth"
                type="text"
                inputmode="numeric"
                placeholder="描边"
                class="h-9 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-indigo-500"
              >
            </div>
            <div class="mt-2 flex justify-end gap-2">
              <button type="button" class="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-slate-500 hover:bg-white" @click="cancelPresetForm">
                取消
              </button>
              <button type="button" class="rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700" @click="upsertDraftPreset">
                {{ editingIndex === null ? '添加' : '更新' }}
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between gap-3 border-t border-slate-100 px-3 py-3">
            <button type="button" class="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100" @click="resetDraftPresets">
              重置
            </button>
            <button
              type="button"
              class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="saving"
              @click="saveDraftPresets"
            >
              {{ saving ? '保存中...' : '保存预设' }}
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ChevronDown, Pencil, Plus, Trash2 } from '@lucide/vue'

import { updatePreviewSizePresets } from '@/api/auth'
import { getErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type { PreviewSizePreset } from '@/types/api'
import { Message } from '@/utils/message'
import {
  buildPreviewSizePresetKey,
  findMatchedPreviewSizePresetIndex,
  normalizePreviewBaseFontSize,
  normalizePreviewIntegerSpec,
  normalizePreviewSizeDimension,
  normalizePreviewSizePresets,
} from './preview-size-presets'

const props = withDefaults(defineProps<{
  currentWidth: number
  currentHeight: number
  currentBaseFontSize?: string
  currentIconDefaultStrokeWidth?: number
  label?: string
  compact?: boolean
  disabled?: boolean
  embedded?: boolean
}>(), {
  label: '',
  compact: false,
  disabled: false,
  embedded: false,
})

const emit = defineEmits<{
  apply: [value: PreviewSizePreset]
  'presets-updated': [value: PreviewSizePreset[]]
}>()

const authStore = useAuthStore()
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const open = ref(false)
const saving = ref(false)
const formVisible = ref(false)
const editingIndex = ref<number | null>(null)
const dropdownStyle = ref<Record<string, string>>({})
const draftPresets = ref<PreviewSizePreset[]>([])
const presetForm = reactive({
  name: '',
  width: '',
  height: '',
  baseFontSize: '',
  iconDefaultStrokeWidth: '',
})

const userPresets = computed(() => normalizePreviewSizePresets(authStore.user?.preview_size_presets))
const matchedPresetIndex = computed(() => findMatchedPreviewSizePresetIndex(
  userPresets.value,
  props.currentWidth,
  props.currentHeight,
  props.currentBaseFontSize,
  props.currentIconDefaultStrokeWidth,
))
const selectedLabel = computed(() => {
  const matchedPreset = matchedPresetIndex.value >= 0 ? userPresets.value[matchedPresetIndex.value] : null
  return matchedPreset ? matchedPreset.name : '自定义尺寸'
})

watch(open, async (visible) => {
  if (!visible) {
    return
  }
  syncDraftPresets()
  await nextTick()
  syncDropdownPosition()
})

onMounted(() => {
  if (!authStore.user) {
    void authStore.ensureLoaded()
  }
  document.addEventListener('mousedown', handleDocumentPointerDown)
  window.addEventListener('resize', syncDropdownPosition)
  document.addEventListener('scroll', syncDropdownPosition, true)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleDocumentPointerDown)
  window.removeEventListener('resize', syncDropdownPosition)
  document.removeEventListener('scroll', syncDropdownPosition, true)
})

/**
 * 展开或收起预设下拉面板。
 */
function toggleDropdown() {
  if (props.disabled) {
    return
  }
  open.value = !open.value
}

/**
 * 将用户已保存预设复制到本地下拉草稿中。
 */
function syncDraftPresets() {
  draftPresets.value = userPresets.value.map(item => ({ ...item }))
}

/**
 * 恢复本轮下拉维护草稿到已保存状态。
 */
function resetDraftPresets() {
  syncDraftPresets()
  cancelPresetForm()
}

/**
 * 应用选中的预设尺寸到外部表单。
 * @param preset 预设尺寸
 */
function applyPreset(preset: PreviewSizePreset) {
  emit('apply', { ...preset })
  open.value = false
}

/**
 * 判断预设是否匹配当前外部尺寸。
 * @param preset 预设尺寸
 */
function isPresetSelected(preset: PreviewSizePreset) {
  return preset.width === props.currentWidth && preset.height === props.currentHeight
}

/**
 * 初始化新增预设表单，默认使用当前位置的尺寸。
 */
function startCreatePreset() {
  editingIndex.value = null
  presetForm.name = ''
  presetForm.width = String(props.currentWidth || 1920)
  presetForm.height = String(props.currentHeight || 1080)
  presetForm.baseFontSize = normalizePreviewBaseFontSize(props.currentBaseFontSize, '20px')
  presetForm.iconDefaultStrokeWidth = String(normalizePreviewIntegerSpec(props.currentIconDefaultStrokeWidth, 2, 1, 64))
  formVisible.value = true
}

/**
 * 初始化编辑预设表单。
 * @param index 预设索引
 */
function startEditPreset(index: number) {
  const preset = draftPresets.value[index]
  if (!preset) {
    return
  }
  editingIndex.value = index
  presetForm.name = preset.name
  presetForm.width = String(preset.width)
  presetForm.height = String(preset.height)
  presetForm.baseFontSize = normalizePreviewBaseFontSize(preset.base_font_size, '20px')
  presetForm.iconDefaultStrokeWidth = String(normalizePreviewIntegerSpec(preset.icon_default_stroke_width, 2, 1, 64))
  formVisible.value = true
}

/**
 * 删除当前草稿中的预设。
 * @param index 预设索引
 */
function deleteDraftPreset(index: number) {
  draftPresets.value.splice(index, 1)
  if (editingIndex.value === index) {
    cancelPresetForm()
  }
}

/**
 * 添加或更新当前草稿中的预设。
 */
function upsertDraftPreset() {
  const name = presetForm.name.trim()
  if (!name) {
    Message.error('请输入预设名称。')
    return
  }
  const width = normalizePreviewSizeDimension(presetForm.width, 0)
  const height = normalizePreviewSizeDimension(presetForm.height, 0)
  if (width <= 0 || height <= 0) {
    Message.error('请输入合法的宽高。')
    return
  }
  const baseFontSize = normalizePreviewBaseFontSize(presetForm.baseFontSize, '')
  if (!baseFontSize) {
    Message.error('请输入合法的基础字号。')
    return
  }
  const iconDefaultStrokeWidth = normalizePreviewIntegerSpec(presetForm.iconDefaultStrokeWidth, 0, 1, 64)
  if (iconDefaultStrokeWidth <= 0) {
    Message.error('请输入合法的图标描边。')
    return
  }
  const nextPreset = {
    name,
    width,
    height,
    base_font_size: baseFontSize,
    icon_default_stroke_width: iconDefaultStrokeWidth,
  }
  if (editingIndex.value === null) {
    draftPresets.value.push(nextPreset)
  } else {
    draftPresets.value.splice(editingIndex.value, 1, nextPreset)
  }
  cancelPresetForm()
}

/**
 * 取消当前新增或编辑表单。
 */
function cancelPresetForm() {
  formVisible.value = false
  editingIndex.value = null
  presetForm.name = ''
  presetForm.width = ''
  presetForm.height = ''
  presetForm.baseFontSize = ''
  presetForm.iconDefaultStrokeWidth = ''
}

/**
 * 保存当前用户的预设尺寸 JSON。
 */
async function saveDraftPresets() {
  saving.value = true
  try {
    const nextPresets = normalizePreviewSizePresets(draftPresets.value)
    const user = await updatePreviewSizePresets(nextPresets)
    authStore.user = user
    syncDraftPresets()
    emit('presets-updated', user.preview_size_presets)
    Message.success('预设尺寸已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存预设尺寸失败。'))
  } finally {
    saving.value = false
  }
}

/**
 * 同步浮层位置，避免被弹窗滚动容器裁切。
 */
function syncDropdownPosition() {
  if (!open.value || !triggerRef.value) {
    return
  }
  const rect = triggerRef.value.getBoundingClientRect()
  const margin = 12
  const panelWidth = Math.max(rect.width, 360)
  const panelHeight = 456
  const spaceBelow = window.innerHeight - rect.bottom - margin
  const spaceAbove = rect.top - margin
  const shouldOpenAbove = spaceBelow < panelHeight && spaceAbove > spaceBelow
  const top = shouldOpenAbove
    ? Math.max(margin, rect.top - panelHeight - 8)
    : Math.min(window.innerHeight - margin - panelHeight, rect.bottom + 8)
  const left = Math.min(rect.left, window.innerWidth - panelWidth - margin)
  dropdownStyle.value = {
    top: `${Math.max(margin, top)}px`,
    left: `${Math.max(margin, left)}px`,
    width: `${panelWidth}px`,
    maxHeight: `${Math.min(panelHeight, window.innerHeight - margin * 2)}px`,
  }
}

/**
 * 点击浮层外部时关闭下拉。
 * @param event 鼠标事件
 */
function handleDocumentPointerDown(event: MouseEvent) {
  if (!open.value) {
    return
  }
  const target = event.target as Node | null
  if (!target) {
    return
  }
  if (rootRef.value?.contains(target) || dropdownRef.value?.contains(target)) {
    return
  }
  open.value = false
}

/**
 * 生成人可读的预设规格摘要。
 * @param preset 预设尺寸规格
 */
function resolvePresetSummary(preset: PreviewSizePreset) {
  const baseFontSize = normalizePreviewBaseFontSize(preset.base_font_size, '20px')
  const iconStroke = normalizePreviewIntegerSpec(preset.icon_default_stroke_width, 2, 1, 64)
  return `${preset.width} × ${preset.height} · ${baseFontSize} · 描边 ${iconStroke}`
}
</script>

<style scoped>
.preset-fade-enter-active,
.preset-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.preset-fade-enter-from,
.preset-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
