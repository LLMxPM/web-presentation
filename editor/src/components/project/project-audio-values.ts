/**
 * 文件功能：维护项目音频设置的 Editor 草稿、校验与 API 映射。
 *
 * 草稿用字符串承接输入中的中间态；提交前统一收敛为严格整数和 cue 绑定，
 * 不把空行、未选资源或非法 interaction key 发送给 Backend。
 */

import type { AudioCueBindingInput, ProjectAudioSettings } from '@/types/api'

export const DEFAULT_AUDIO_MASTER_VOLUME_PERCENT = 100
export const DEFAULT_AUDIO_NARRATION_VOLUME_PERCENT = 100
export const DEFAULT_AUDIO_EFFECTS_VOLUME_PERCENT = 30
export const DEFAULT_CUE_GAIN_PERCENT = 100

export const TRANSITION_CUE_KEYS = {
  forward: 'transition.forward',
  backward: 'transition.backward',
} as const

const INTERACTION_CUE_PATTERN = /^interaction\.[a-z0-9_-]+(?:\.[a-z0-9_-]+)*$/

export interface AudioCueBindingDraft {
  /** 交互 cue 的语义 key；切页行由固定 key 提供。 */
  key: string
  /** 资源 ID 的字符串形式；空串表示未绑定。 */
  assetId: string
  gainPercent: string
}

export interface AudioSettingsDraft {
  masterVolume: string
  narrationVolume: string
  effectsVolume: string
  transitionForward: AudioCueBindingDraft
  transitionBackward: AudioCueBindingDraft
  interactionCues: AudioCueBindingDraft[]
}

/** 创建空绑定行。 */
function createBindingDraft(assetId = '', gainPercent = DEFAULT_CUE_GAIN_PERCENT): AudioCueBindingDraft {
  return { key: '', assetId, gainPercent: String(gainPercent) }
}

/** 创建默认音频草稿：默认音量且不绑定 cue。 */
export function createAudioSettingsDraft(settings?: ProjectAudioSettings | null): AudioSettingsDraft {
  const draft: AudioSettingsDraft = {
    masterVolume: String(settings?.master_volume_percent ?? DEFAULT_AUDIO_MASTER_VOLUME_PERCENT),
    narrationVolume: String(settings?.narration_volume_percent ?? DEFAULT_AUDIO_NARRATION_VOLUME_PERCENT),
    effectsVolume: String(settings?.effects_volume_percent ?? DEFAULT_AUDIO_EFFECTS_VOLUME_PERCENT),
    transitionForward: createBindingDraft(),
    transitionBackward: createBindingDraft(),
    interactionCues: [],
  }
  for (const binding of settings?.cue_bindings ?? []) {
    const target = {
      key: binding.key,
      assetId: String(binding.asset_id),
      gainPercent: String(binding.gain_percent ?? DEFAULT_CUE_GAIN_PERCENT),
    }
    if (binding.key === TRANSITION_CUE_KEYS.forward) draft.transitionForward = target
    else if (binding.key === TRANSITION_CUE_KEYS.backward) draft.transitionBackward = target
    else draft.interactionCues.push(target)
  }
  draft.interactionCues.sort((left, right) => left.key.localeCompare(right.key))
  return draft
}

/** 判断交互 cue key 是否符合首版命名空间。 */
export function isValidInteractionCueKey(key: string): boolean {
  return INTERACTION_CUE_PATTERN.test(key.trim())
}

/** 严格解析 0–100 的整数字符串；空值或小数返回 null。 */
function parsePercent(value: string): number | null {
  const normalized = value.trim()
  if (!/^\d{1,3}$/.test(normalized)) return null
  const numeric = Number(normalized)
  return numeric >= 0 && numeric <= 100 ? numeric : null
}

/**
 * 校验完整音频草稿。
 * @returns 第一条人类可读错误；全部合法时返回 null
 */
export function validateAudioSettingsDraft(draft: AudioSettingsDraft): string | null {
  for (const [label, value] of [
    ['主音量', draft.masterVolume],
    ['旁白音量', draft.narrationVolume],
    ['音效音量', draft.effectsVolume],
  ] as const) {
    if (parsePercent(value) === null) return `${label}必须是 0–100 的整数。`
  }

  const rows: Array<{ label: string; key: string; binding: AudioCueBindingDraft; keyEditable: boolean }> = [
    { label: '前进切页音效', key: TRANSITION_CUE_KEYS.forward, binding: draft.transitionForward, keyEditable: false },
    { label: '后退切页音效', key: TRANSITION_CUE_KEYS.backward, binding: draft.transitionBackward, keyEditable: false },
    ...draft.interactionCues.map((binding, index) => ({
      label: `交互音效 ${index + 1}`,
      key: binding.key,
      binding,
      keyEditable: true,
    })),
  ]
  const seenKeys = new Set<string>()
  for (const row of rows) {
    const hasAsset = Boolean(row.binding.assetId)
    if (!row.keyEditable) {
      // 切页行的固定 key 不是用户输入；未绑定资源时整行跳过。
      if (!hasAsset) continue
      if (parsePercent(row.binding.gainPercent) === null) return `${row.label}的绑定增益必须是 0–100 的整数。`
      continue
    }
    const key = row.key.trim()
    if (!key && !hasAsset) continue
    if (!isValidInteractionCueKey(key)) {
      return `${row.label}的 key 必须形如 interaction.confirm。`
    }
    if (seenKeys.has(key)) return `${row.label}的 cue key 重复：${key}。`
    seenKeys.add(key)
    if (!hasAsset) return `${row.label}已填写 key，但还没有选择音频资源。`
    if (parsePercent(row.binding.gainPercent) === null) return `${row.label}的绑定增益必须是 0–100 的整数。`
  }
  return null
}

/** 汇总所有已绑定 cue 的 API 结构，未绑定行不提交。 */
export function normalizeAudioSettingsDraft(draft: AudioSettingsDraft): ProjectAudioSettings {
  const cueBindings: AudioCueBindingInput[] = []
  const append = (key: string, binding: AudioCueBindingDraft, keyEditable: boolean): void => {
    if (!binding.assetId) return
    const normalizedKey = keyEditable ? binding.key.trim() : key
    if (!normalizedKey) return
    cueBindings.push({
      key: normalizedKey,
      asset_id: Number(binding.assetId),
      gain_percent: Number(binding.gainPercent),
    })
  }
  append(TRANSITION_CUE_KEYS.forward, draft.transitionForward, false)
  append(TRANSITION_CUE_KEYS.backward, draft.transitionBackward, false)
  for (const binding of draft.interactionCues) {
    append(binding.key, binding, true)
  }
  return {
    master_volume_percent: Number(draft.masterVolume),
    narration_volume_percent: Number(draft.narrationVolume),
    effects_volume_percent: Number(draft.effectsVolume),
    cue_bindings: cueBindings,
  }
}

/** 计算 cue 最终音量百分比：主音量 × 音效音量 × 绑定增益。 */
export function calculateCueGainPercent(
  masterVolume: string,
  effectsVolume: string,
  gainPercent: string,
): number | null {
  const master = parsePercent(masterVolume)
  const effects = parsePercent(effectsVolume)
  const gain = parsePercent(gainPercent)
  if (master === null || effects === null || gain === null) return null
  return Math.round((master * effects * gain) / 100) / 100
}

/** 格式化最终增益，整数不补小数位。 */
export function formatCueGainPercent(value: number | null): string {
  if (value === null) return '待填写'
  const rounded = Math.round((value + Number.EPSILON) * 10) / 10
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)}%`
}
