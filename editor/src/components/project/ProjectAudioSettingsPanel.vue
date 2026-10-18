<!-- 文件功能：项目音频设置面板，编辑三段音量、切页与交互 cue，并提供显式试听。 -->
<template>
  <div class="grid gap-4">
    <section class="rounded-lg border border-border bg-surface p-4">
      <h3 class="text-sm font-semibold text-text-emphasis">音量</h3>
      <p class="mt-0.5 text-xs leading-5 text-text-disabled">
        主音量同时作用于旁白与 cue；音效音量只影响切页和交互 cue。页面内联音量仍在页面源码中设置。
      </p>
      <div class="mt-3 grid gap-3 sm:grid-cols-3">
        <UiFormField label="主音量">
          <template #default="field">
            <UiInput
              :model-value="draft.masterVolume"
              type="number"
              min="0"
              max="100"
              step="1"
              :input-id="field.inputId"
              :described-by="field.describedBy"
              @update:model-value="updateVolume('masterVolume', $event)"
            >
              <template #suffix>%</template>
            </UiInput>
          </template>
        </UiFormField>
        <UiFormField label="旁白音量">
          <template #default="field">
            <UiInput
              :model-value="draft.narrationVolume"
              type="number"
              min="0"
              max="100"
              step="1"
              :input-id="field.inputId"
              :described-by="field.describedBy"
              @update:model-value="updateVolume('narrationVolume', $event)"
            >
              <template #suffix>%</template>
            </UiInput>
          </template>
        </UiFormField>
        <UiFormField label="音效音量">
          <template #default="field">
            <UiInput
              :model-value="draft.effectsVolume"
              type="number"
              min="0"
              max="100"
              step="1"
              :input-id="field.inputId"
              :described-by="field.describedBy"
              @update:model-value="updateVolume('effectsVolume', $event)"
            >
              <template #suffix>%</template>
            </UiInput>
          </template>
        </UiFormField>
      </div>
      <p class="mt-2 text-xs text-text-disabled">0 表示静音；cue 的最终音量为主音量 × 音效音量 × 绑定增益。</p>
    </section>

    <section class="rounded-lg border border-border bg-surface p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div class="min-w-0">
          <h3 class="text-sm font-semibold text-text-emphasis">音效资源</h3>
          <p class="mt-0.5 text-xs leading-5 text-text-disabled">只列出当前工作空间 active 的音频资源；切页 cue 只有一个通道，新音效会替换上一段。</p>
        </div>
        <UiButton variant="ghost" size="sm" :loading="assetsLoading" @click="loadAssets">刷新资源</UiButton>
      </div>

      <p v-if="assetsLoading" class="mt-3 rounded-lg border border-border bg-canvas px-3 py-2 text-xs text-text-muted" role="status">
        正在加载音频资源…
      </p>
      <div v-else-if="assetsError" class="mt-3 rounded-lg border border-danger-border bg-danger-muted px-3 py-2 text-xs text-danger-strong" role="alert">
        <p>{{ assetsError }}</p>
        <UiButton variant="ghost" size="sm" class="mt-2" @click="loadAssets">重试</UiButton>
      </div>
      <p v-else-if="assets.length === 0" class="mt-3 rounded-lg border border-dashed border-border px-3 py-4 text-xs leading-5 text-text-muted">
        当前工作空间还没有可用音频资源。请先在资源库上传 MP3、M4A、AAC、OGG 或 WAV 文件，再回来绑定 cue。
      </p>

      <template v-else>
        <div class="mt-4 space-y-3">
          <article
            v-for="row in cueRows"
            :key="row.id"
            class="rounded-lg border border-border bg-canvas/60 p-3"
            :data-audio-cue-row="row.id"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="min-w-0">
                <h4 class="text-sm font-semibold text-text">{{ row.label }}</h4>
                <p class="mt-0.5 text-[11px] leading-5 text-text-disabled">{{ row.hint }}</p>
              </div>
              <div class="flex shrink-0 items-center gap-1">
                <UiButton
                  variant="ghost"
                  size="sm"
                  :disabled="!row.binding.assetId"
                  @click="togglePreview(row)"
                >
                  {{ previewingId === row.id ? '停止试听' : '试听' }}
                </UiButton>
                <UiButton
                  variant="ghost"
                  size="sm"
                  :disabled="row.interactionIndex === null && !row.binding.assetId"
                  @click="clearRow(row)"
                >
                  {{ row.keyEditable ? '删除' : '清空' }}
                </UiButton>
              </div>
            </div>

            <div class="mt-2 grid gap-2 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1.4fr)_110px]">
              <UiFormField :label="row.keyEditable ? '语义 key' : '固定 key'">
                <template #default="field">
                  <UiInput
                    v-if="row.keyEditable"
                    :model-value="row.binding.key"
                    placeholder="interaction.confirm"
                    :input-id="field.inputId"
                    :described-by="field.describedBy"
                    :invalid="Boolean(row.binding.key) && !isValidInteractionCueKey(row.binding.key)"
                    @update:model-value="updateBinding(row, { key: $event })"
                  />
                  <UiInput
                    v-else
                    :model-value="row.key"
                    readonly
                    :input-id="field.inputId"
                    :described-by="field.describedBy"
                  />
                </template>
              </UiFormField>
              <UiFormField label="音效资源">
                <template #default="field">
                  <UiSelect
                    :model-value="row.binding.assetId"
                    :options="assetOptions"
                    placeholder="未绑定"
                    :id="field.inputId"
                    :aria-describedby="field.describedBy"
                    @update:model-value="updateBinding(row, { assetId: String($event ?? '') })"
                  />
                </template>
              </UiFormField>
              <UiFormField label="绑定增益">
                <template #default="field">
                  <UiInput
                    :model-value="row.binding.gainPercent"
                    type="number"
                    min="0"
                    max="100"
                    step="1"
                    :input-id="field.inputId"
                    :described-by="field.describedBy"
                    @update:model-value="updateBinding(row, { gainPercent: $event })"
                  >
                    <template #suffix>%</template>
                  </UiInput>
                </template>
              </UiFormField>
            </div>
            <p class="mt-2 text-[11px] text-text-disabled">
              最终音量：{{ formatCueGainPercent(calculateCueGainPercent(draft.masterVolume, draft.effectsVolume, row.binding.gainPercent)) }}
              <span v-if="row.keyEditable && row.binding.key && !isValidInteractionCueKey(row.binding.key)" class="ml-1 text-danger-strong">
                key 需形如 interaction.confirm
              </span>
            </p>
          </article>
        </div>

        <div class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
          <p class="text-xs leading-5 text-text-disabled">
            交互音效由页面业务 handler 主动触发；同一 key 80ms 内只播放一次，最多同时 4 路。
          </p>
          <UiButton variant="secondary" size="sm" @click="addInteractionCue">添加交互音效</UiButton>
        </div>
      </template>

      <p v-if="previewError" class="mt-2 rounded-lg border border-danger-border bg-danger-muted px-3 py-2 text-xs text-danger-strong" role="alert">
        {{ previewError }}
      </p>
    </section>

    <section class="rounded-lg border border-border bg-surface p-4">
      <h3 class="text-sm font-semibold text-text-emphasis">执行范围</h3>
      <ul class="mt-2 space-y-1 text-xs leading-5 text-text-disabled">
        <li>切页与交互音效只在全屏放映或演讲者观众窗口播放。</li>
        <li>普通预览、卡片、缩略图、截图、导出和打印均保持静音。</li>
        <li>项目未绑定或资源不可用时，cue 静默跳过，不阻塞导航和业务动作。</li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { listWorkspaceAssets } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import { UiButton, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { AssetResponse } from '@/types/api'
import {
  TRANSITION_CUE_KEYS,
  calculateCueGainPercent,
  formatCueGainPercent,
  isValidInteractionCueKey,
  type AudioCueBindingDraft,
  type AudioSettingsDraft,
} from './project-audio-values'

type VolumeField = 'masterVolume' | 'narrationVolume' | 'effectsVolume'

interface CueRow {
  id: string
  label: string
  hint: string
  key: string
  keyEditable: boolean
  interactionIndex: number | null
  binding: AudioCueBindingDraft
}

const props = defineProps<{
  workspaceId: number | null
  draft: AudioSettingsDraft
}>()

const emit = defineEmits<{
  'update:draft': [value: AudioSettingsDraft]
}>()

const assets = ref<AssetResponse[]>([])
const assetsLoading = ref(false)
const assetsError = ref('')
const previewingId = ref<string | null>(null)
const previewError = ref('')
let previewElement: HTMLAudioElement | null = null

const assetOptions = computed(() => assets.value.map(asset => ({
  label: asset.name,
  value: String(asset.id),
})))

const assetById = computed(() => new Map(assets.value.map(asset => [String(asset.id), asset])))

/** 组装切页与交互 cue 行，交互行保留草稿索引用于不可变更新。 */
const cueRows = computed<CueRow[]>(() => [
  {
    id: 'transition-forward',
    label: '前进切页',
    hint: '从上一页进入下一页时播放，快速连跳会替换上一段。',
    key: TRANSITION_CUE_KEYS.forward,
    keyEditable: false,
    interactionIndex: null,
    binding: props.draft.transitionForward,
  },
  {
    id: 'transition-backward',
    label: '后退切页',
    hint: '从后面的页面返回上一页时播放。',
    key: TRANSITION_CUE_KEYS.backward,
    keyEditable: false,
    interactionIndex: null,
    binding: props.draft.transitionBackward,
  },
  ...props.draft.interactionCues.map((binding, index) => ({
    id: `interaction-${index}`,
    label: `交互音效 ${index + 1}`,
    hint: '由页面业务代码按语义 key 主动触发。',
    key: binding.key,
    keyEditable: true,
    interactionIndex: index,
    binding,
  })),
])

/** 用新对象替换草稿，保证父级脏检查与撤销基线一致。 */
function emitDraft(next: AudioSettingsDraft): void {
  emit('update:draft', next)
}

/** 更新三段音量中的一项。 */
function updateVolume(field: VolumeField, value: string): void {
  emitDraft({ ...props.draft, [field]: value })
}

/** 更新切页或交互 cue 行；交互行按索引替换。 */
function updateBinding(row: CueRow, patch: Partial<AudioCueBindingDraft>): void {
  // 替换资源时停止旧试听，避免继续播放已不在该行上的声音。
  if (
    previewingId.value === row.id
    && patch.assetId !== undefined
    && patch.assetId !== row.binding.assetId
  ) {
    stopPreview(true)
  }
  if (row.interactionIndex === null) {
    const key = row.id === 'transition-forward' ? 'transitionForward' : 'transitionBackward'
    emitDraft({
      ...props.draft,
      [key]: { ...props.draft[key], ...patch },
    })
    return
  }
  const interactionCues = props.draft.interactionCues.map((binding, index) => (
    index === row.interactionIndex ? { ...binding, ...patch } : binding
  ))
  emitDraft({ ...props.draft, interactionCues })
}

/** 清空一行的绑定；交互行直接移除，切页行保留固定 key。 */
function clearRow(row: CueRow): void {
  stopPreview()
  if (row.interactionIndex === null) {
    updateBinding(row, { assetId: '', gainPercent: '100' })
    return
  }
  emitDraft({
    ...props.draft,
    interactionCues: props.draft.interactionCues.filter((_, index) => index !== row.interactionIndex),
  })
}

/** 追加一条空白交互 cue。 */
function addInteractionCue(): void {
  emitDraft({
    ...props.draft,
    interactionCues: [...props.draft.interactionCues, { key: '', assetId: '', gainPercent: '100' }],
  })
}

/** 停止试听并清空播放态；不重置错误提示，除非调用方显式要求。 */
function stopPreview(clearError = false): void {
  if (previewElement) {
    previewElement.pause()
    try {
      previewElement.currentTime = 0
    }
    catch {
      // 媒体尚未加载元数据时浏览器可能拒绝写入 currentTime。
    }
  }
  previewElement = null
  previewingId.value = null
  if (clearError) previewError.value = ''
}

/** 由显式按钮触发试听；再次点击同一行停止。 */
function togglePreview(row: CueRow): void {
  const wasPreviewing = previewingId.value === row.id
  stopPreview(true)
  if (wasPreviewing) return

  const asset = assetById.value.get(row.binding.assetId)
  if (!asset?.url) {
    previewError.value = '该资源没有可用的试听地址，请刷新资源后重试。'
    return
  }
  const gainPercent = calculateCueGainPercent(props.draft.masterVolume, props.draft.effectsVolume, row.binding.gainPercent)
  if (gainPercent === null) {
    previewError.value = '请先填写合法的音量和绑定增益。'
    return
  }
  try {
    const element = new Audio(asset.url)
    element.preload = 'auto'
    element.volume = Math.min(1, Math.max(0, gainPercent / 100))
    element.onended = () => stopPreview()
    previewElement = element
    previewingId.value = row.id
    void element.play().catch(() => {
      previewError.value = '无法播放该音频，请检查文件编码或访问权限。'
      stopPreview()
    })
  }
  catch {
    previewError.value = '当前浏览器无法创建音频试听。'
    stopPreview()
  }
}

/** 音量、音效音量或绑定增益变化时同步试听元素，不重启播放。 */
function updatePreviewVolume(): void {
  const row = cueRows.value.find(item => item.id === previewingId.value)
  if (!previewElement || !row) return
  const gainPercent = calculateCueGainPercent(props.draft.masterVolume, props.draft.effectsVolume, row.binding.gainPercent)
  if (gainPercent !== null) previewElement.volume = Math.min(1, Math.max(0, gainPercent / 100))
}

watch(
  () => [
    props.draft.masterVolume,
    props.draft.effectsVolume,
    props.draft.transitionForward.gainPercent,
    props.draft.transitionBackward.gainPercent,
    ...props.draft.interactionCues.map(binding => binding.gainPercent),
  ] as const,
  updatePreviewVolume,
)

/** 读取当前工作空间 active 音频资源，供选择器与试听使用。 */
async function loadAssets(): Promise<void> {
  stopPreview(true)
  if (!props.workspaceId) {
    assets.value = []
    assetsError.value = '缺少工作空间上下文，暂时不能加载音频资源。'
    return
  }
  assetsLoading.value = true
  assetsError.value = ''
  try {
    const response = await listWorkspaceAssets(props.workspaceId, {
      assetType: 'audio',
      status: 'active',
      page: 1,
      page_size: 100,
    })
    assets.value = response.items
  }
  catch (error) {
    assets.value = []
    assetsError.value = getErrorMessage(error, '加载音频资源失败。')
  }
  finally {
    assetsLoading.value = false
  }
}

watch(() => props.workspaceId, () => { void loadAssets() })
onMounted(() => { void loadAssets() })
onBeforeUnmount(() => stopPreview(true))

defineExpose({ stopPreview })
</script>
