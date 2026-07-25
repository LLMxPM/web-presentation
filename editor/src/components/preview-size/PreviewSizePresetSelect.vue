<!-- 文件功能：提供用户级预设尺寸的下拉选择与维护入口，可在各类页面尺寸配置位置复用。 -->
<template>
  <div class="relative w-full" :class="embedded ? 'h-full' : ''">
    <label v-if="label" class="mb-1.5 block text-sm font-medium text-text">{{ label }}</label>
    <UiPopover
      :open="open"
      side="bottom"
      align="start"
      :side-offset="8"
      content-class="w-[360px] max-w-[calc(100vw-24px)] max-h-[456px] !overflow-hidden !border-border !bg-surface !p-0 shadow-popover"
      @update:open="open = $event"
    >
      <template #trigger>
        <UiButton
          :variant="embedded ? 'ghost' : 'secondary'"
          :size="embedded || !compact ? 'lg' : 'md'"
          content-align="between"
          class="w-full text-left"
          :disabled="disabled"
          :aria-expanded="open"
          aria-haspopup="dialog"
        >
          <span class="min-w-0 flex-1">
            <span class="block truncate font-medium">{{ selectedLabel }}</span>
            <span v-if="!compact" class="block truncate text-xs leading-tight text-text-muted">{{ currentWidth }} × {{ currentHeight }}</span>
          </span>
          <ChevronDown class="h-4 w-4 shrink-0 text-text-muted transition-transform" :class="open ? 'rotate-180' : ''" />
        </UiButton>
      </template>

      <div>
        <div class="flex items-center justify-between gap-3 border-b border-border px-3 py-2.5">
          <div class="text-sm font-semibold text-text">我的尺寸模板</div>
          <UiButton
            variant="ghost"
            size="sm"
            @click="startCreatePreset"
          >
            <Plus class="h-3.5 w-3.5" />
            新增
          </UiButton>
        </div>

          <div class="max-h-[240px] overflow-y-auto py-1">
            <div v-if="draftPresets.length === 0" class="px-4 py-8 text-center text-sm text-text-muted">
              暂无预设，可新增后保存。
            </div>

            <div
              v-for="(preset, index) in draftPresets"
              :key="buildPreviewSizePresetKey(preset, index)"
              class="group flex items-center gap-1 px-2 py-1 transition-colors hover:bg-surface-hover"
              :class="isPresetSelected(preset) ? 'bg-accent-muted' : ''"
            >
              <UiButton
                variant="ghost"
                size="lg"
                content-align="start"
                class="min-w-0 flex-1 text-left"
                :aria-pressed="isPresetSelected(preset)"
                @click="applyPreset(preset)"
              >
                <span class="flex h-4 w-4 shrink-0 items-center justify-center text-accent" aria-hidden="true">
                  <Check v-if="isPresetSelected(preset)" class="h-3.5 w-3.5" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-sm font-medium text-text">{{ preset.name }}</span>
                  <span class="block truncate text-xs text-text-muted">{{ resolvePresetSummary(preset) }}</span>
                </span>
              </UiButton>
              <UiIconButton
                label="编辑"
                size="xs"
                @click="startEditPreset(index)"
              >
                <Pencil class="h-3.5 w-3.5" />
              </UiIconButton>
              <UiIconButton
                label="删除"
                size="xs"
                @click="deleteDraftPreset(index)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </UiIconButton>
            </div>
          </div>

          <div v-if="formVisible" class="border-t border-border bg-surface-muted p-3">
            <div class="grid grid-cols-[minmax(0,1.2fr)_84px_84px] gap-2">
              <UiInput
                v-model="presetForm.name"
                placeholder="名称"
                aria-label="预设名称"
              />
              <UiInput
                v-model="presetForm.width"
                inputmode="numeric"
                placeholder="宽"
                aria-label="预设宽度"
              />
              <UiInput
                v-model="presetForm.height"
                inputmode="numeric"
                placeholder="高"
                aria-label="预设高度"
              />
            </div>
            <div class="mt-2 grid grid-cols-2 gap-2">
              <UiInput
                v-model="presetForm.baseFontSize"
                placeholder="字号"
                aria-label="基础字号"
              />
              <UiInput
                v-model="presetForm.iconDefaultStrokeWidth"
                inputmode="numeric"
                placeholder="描边"
                aria-label="图标描边"
              />
            </div>
            <div class="mt-2 flex justify-end gap-2">
              <UiButton variant="ghost" size="xs" @click="cancelPresetForm">
                取消
              </UiButton>
              <UiButton variant="primary" size="xs" @click="upsertDraftPreset">
                {{ editingIndex === null ? '添加' : '更新' }}
              </UiButton>
            </div>
          </div>

          <div class="flex items-center justify-between gap-3 border-t border-border px-3 py-2.5">
            <UiButton variant="ghost" size="xs" @click="resetDraftPresets">
              重置
            </UiButton>
            <UiButton
              variant="primary"
              size="xs"
              :disabled="saving"
              @click="saveDraftPresets"
            >
              {{ saving ? '保存中...' : '保存预设' }}
            </UiButton>
          </div>
      </div>
    </UiPopover>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Check, ChevronDown, Pencil, Plus, Trash2 } from '@lucide/vue'

import { updatePreviewSizePresets } from '@/api/auth'
import { getErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { UiButton, UiIconButton, UiInput, UiPopover } from '@/components/ui'
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
const open = ref(false)
const saving = ref(false)
const formVisible = ref(false)
const editingIndex = ref<number | null>(null)
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
})

onMounted(() => {
  if (!authStore.user) {
    void authStore.ensureLoaded()
  }
})


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
 * 生成人可读的预设规格摘要。
 * @param preset 预设尺寸规格
 */
function resolvePresetSummary(preset: PreviewSizePreset) {
  const baseFontSize = normalizePreviewBaseFontSize(preset.base_font_size, '20px')
  const iconStroke = normalizePreviewIntegerSpec(preset.icon_default_stroke_width, 2, 1, 64)
  return `${preset.width} × ${preset.height} · ${baseFontSize} · 描边 ${iconStroke}`
}
</script>

