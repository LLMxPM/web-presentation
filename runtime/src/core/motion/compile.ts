/**
 * 文件功能：把 page-timeline.v1 定义编译为确定性、可序列化的规范计划。
 *
 * 编译只处理标签、前后依赖、裁切、速率、重复、属性所有权与海报边界；
 * 不读取 DOM、不播放媒体、不执行作者提供的视觉函数，也不猜测资源真实时长。
 */
import {
  MAX_MOTION_DURATION_MS,
  MAX_MOTION_REPEAT,
  MAX_MOTION_TRACKS,
  MOTION_PLAN_SCHEMA_VERSION,
  PAGE_TIMELINE_SCHEMA_VERSION,
  type CompiledDomTrack,
  type CompiledMediaTrack,
  type CompiledModelTrack,
  type CompiledMotionPlan,
  type CompiledMotionTrack,
  type DomMotionPreset,
  type DomMotionProperty,
  type DomMotionState,
  type ModelClipReference,
  type ModelMotionTransformState,
  type MotionEndBehavior,
  type MotionMediaType,
  type MotionTrackDefinition,
  type MotionTrackRole,
  type PageTimelineDefinition,
} from './types'
import {
  MOTION_ERROR_DEPENDENCY_CYCLE,
  MOTION_ERROR_DURATION_UNRESOLVED,
  MOTION_ERROR_PROPERTY_CONFLICT,
  MOTION_ERROR_SCHEMA_INVALID,
  MOTION_ERROR_TARGET_INVALID,
  MotionError,
  toMotionError,
} from './errors'

const TIMELINE_ID_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/
const TRACK_ID_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/
const MAX_SELECTOR_LENGTH = 500
const MAX_ASSET_NAME_LENGTH = 200
const MIN_RATE = 0.1
const MAX_RATE = 8
const MAX_ABSOLUTE_DOM_VALUE = 100_000

const PRESET_STATES: Record<DomMotionPreset, { from: DomMotionState; to: DomMotionState }> = {
  fade: { from: { opacity: 0 }, to: { opacity: 1 } },
  'fade-up': { from: { opacity: 0, y: 24 }, to: { opacity: 1, y: 0 } },
  'scale-in': { from: { opacity: 0, scale: 0.96 }, to: { opacity: 1, scale: 1 } },
}

const DOM_PROPERTY_DEFAULTS: Required<DomMotionState> = {
  opacity: 1,
  x: 0,
  y: 0,
  scale: 1,
  rotation: 0,
}

const DOM_PROPERTIES: DomMotionProperty[] = ['opacity', 'x', 'y', 'scale', 'rotation']

const MODEL_TRANSFORM_DEFAULTS: Required<ModelMotionTransformState> = {
  x: 0,
  y: 0,
  z: 0,
  scale: 1,
  rotationY: 0,
}

/** 编译输入校验与结果；调用方按 planDigest 判断定义是否变化。 */
export interface CompileMotionOptions {
  /** 兼容未标注版本的历史调用；缺省要求显式 schemaVersion=1。 */
  allowMissingSchemaVersion?: boolean
}

/**
 * 编译规范计划。任何非法字段都抛 MotionError，并携带 fieldPath/trackId。
 */
export function compilePageTimeline(
  definition: PageTimelineDefinition,
  options: CompileMotionOptions = {},
): CompiledMotionPlan {
  const rootPath = 'timeline'
  if (!definition || typeof definition !== 'object') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '编排定义必须是对象。', { fieldPath: rootPath })
  }
  if (definition.schemaVersion !== PAGE_TIMELINE_SCHEMA_VERSION) {
    if (!(options.allowMissingSchemaVersion && definition.schemaVersion === undefined)) {
      throw new MotionError(
        MOTION_ERROR_SCHEMA_INVALID,
        `不支持的编排定义版本 ${String(definition.schemaVersion)}。`,
        { fieldPath: 'timeline.schemaVersion' },
      )
    }
  }
  const timelineId = requireString(definition.timelineId, 'timeline.timelineId', 64)
  if (!TIMELINE_ID_PATTERN.test(timelineId)) {
    throw new MotionError(
      MOTION_ERROR_SCHEMA_INVALID,
      'timelineId 必须以字母开头，只包含字母、数字、下划线和短横线（最长 64）。',
      { fieldPath: 'timeline.timelineId' },
    )
  }
  const rawTracks = definition.tracks
  if (!Array.isArray(rawTracks)) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'tracks 必须是数组。', { fieldPath: 'timeline.tracks' })
  }
  if (rawTracks.length === 0) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '时间轴至少需要一个轨道。', { fieldPath: 'timeline.tracks' })
  }
  if (rawTracks.length > MAX_MOTION_TRACKS) {
    throw new MotionError(
      MOTION_ERROR_SCHEMA_INVALID,
      `时间轴轨道数超过上限 ${MAX_MOTION_TRACKS}。`,
      { fieldPath: 'timeline.tracks' },
    )
  }

  const ids = new Set<string>()
  const labels = new Map<string, string>()
  for (const [index, track] of rawTracks.entries()) {
    const path = `timeline.tracks[${index}]`
    if (!track || typeof track !== 'object') {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '轨道必须是对象。', { fieldPath: path })
    }
    const id = requireString(track.id, `${path}.id`, 64)
    if (!TRACK_ID_PATTERN.test(id)) {
      throw new MotionError(
        MOTION_ERROR_SCHEMA_INVALID,
        '轨道 id 必须以字母开头，只包含字母、数字、下划线和短横线（最长 64）。',
        { fieldPath: `${path}.id`, trackId: id },
      )
    }
    if (ids.has(id)) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `轨道 id ${id} 重复。`, {
        fieldPath: `${path}.id`,
        trackId: id,
      })
    }
    ids.add(id)
    if (track.label !== undefined) {
      const label = requireString(track.label, `${path}.label`, 64)
      if (ids.has(label)) {
        throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `标签 ${label} 与轨道 id 冲突。`, {
          fieldPath: `${path}.label`,
          trackId: id,
        })
      }
      if (labels.has(label)) {
        throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `标签 ${label} 重复。`, {
          fieldPath: `${path}.label`,
          trackId: id,
        })
      }
      labels.set(label, id)
    }
  }

  let primaryClockTrackId: string | null = null
  let narrationSeen = false
  let audibleSeen = false
  const compiledByIndex: Array<CompiledMotionTrack | null> = rawTracks.map(() => null)
  const compiling = new Set<number>()
  const indexById = new Map(rawTracks.map((track, index) => [track.id, index]))
  const indexByLabel = new Map<string, number>()
  rawTracks.forEach((track, index) => {
    if (track.label !== undefined) indexByLabel.set(track.label, index)
  })

  /** 递归解析轨道起点；同时检测依赖环与缺失前驱。 */
  function resolveStart(index: number): { startMs: number; endMs: number; durationMs: number } {
    const existing = compiledByIndex[index]
    if (existing) return { startMs: existing.startMs, endMs: existing.endMs, durationMs: existing.durationMs }
    if (compiling.has(index)) {
      const track = rawTracks[index]
      throw new MotionError(
        MOTION_ERROR_DEPENDENCY_CYCLE,
        `轨道 ${track.id} 存在循环依赖。`,
        { fieldPath: `timeline.tracks[${index}].afterTrack`, trackId: track.id },
      )
    }
    compiling.add(index)
    const track = rawTracks[index]
    const path = `timeline.tracks[${index}]`
    const endBehavior = resolveEndBehavior(track, path)
    const role = resolveRole(track, path)
    const required = resolveRequired(track, role)
    let durationMs = 0
    let startMs = 0
    let compiled: CompiledMotionTrack

    if (track.type === 'dom') {
      const dom = compileDomTrack(track, index, role, required)
      durationMs = dom.durationMs
      compiled = dom
    } else if (track.type === 'audio' || track.type === 'video') {
      const media = compileMediaTrack(track, index, role, required, endBehavior)
      durationMs = media.durationMs
      compiled = media
      if (role === 'primary') {
        if (primaryClockTrackId) {
          throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '时间轴最多只能有一个主媒体时钟。', {
            fieldPath: `${path}.role`,
            trackId: track.id,
          })
        }
        primaryClockTrackId = track.id
      }
      if (role === 'narration') {
        if (narrationSeen) {
          throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '同一时间轴最多只能有一个旁白轨道。', {
            fieldPath: `${path}.role`,
            trackId: track.id,
          })
        }
        narrationSeen = true
      }
      if (!media.muted) {
        if (audibleSeen) {
          throw new MotionError(
            MOTION_ERROR_SCHEMA_INVALID,
            '同步时间轴最多只能有一个有声媒体；辅助同步视频必须静音。',
            { fieldPath: `${path}.muted`, trackId: track.id },
          )
        }
        audibleSeen = true
      }
    } else if (track.type === 'model3d') {
      compiled = compileModelTrack(track, index, role, required, endBehavior)
      durationMs = compiled.durationMs
    } else {
      throw new MotionError(
        MOTION_ERROR_UNSUPPORTED_TYPE,
        `不支持的轨道类型 ${String((track as { type?: unknown }).type)}。`,
        { fieldPath: `${path}.type`, trackId: track.id },
      )
    }

    if (durationMs <= 0 || !Number.isFinite(durationMs)) {
      throw new MotionError(MOTION_ERROR_DURATION_UNRESOLVED, '轨道时长必须为有限正数。', {
        fieldPath: `${path}.durationMs`,
        trackId: track.id,
      })
    }

    const hasStart = track.startMs !== undefined
    const hasAfter = track.afterTrack !== undefined
    if (hasStart && hasAfter) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'startMs 与 afterTrack 不能同时声明。', {
        fieldPath: `${path}.startMs`,
        trackId: track.id,
      })
    }
    if (hasStart) {
      startMs = requireNumber(track.startMs, `${path}.startMs`, track.id)
      if (startMs < 0) {
        throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'startMs 不得小于 0。', {
          fieldPath: `${path}.startMs`,
          trackId: track.id,
        })
      }
    } else if (hasAfter) {
      const afterTrack = requireString(track.afterTrack, `${path}.afterTrack`, 64)
      const dependencyIndex = indexById.get(afterTrack) ?? indexByLabel.get(afterTrack)
      if (dependencyIndex === undefined) {
        throw new MotionError(MOTION_ERROR_TARGET_INVALID, `前驱轨道 ${afterTrack} 不存在。`, {
          fieldPath: `${path}.afterTrack`,
          trackId: track.id,
        })
      }
      const offsetMs = track.offsetMs === undefined ? 0 : requireNumber(track.offsetMs, `${path}.offsetMs`, track.id)
      const dependency = resolveStart(dependencyIndex)
      startMs = dependency.endMs + offsetMs
      if (startMs < 0) {
        throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'afterTrack 与负偏移计算出的起点小于 0。', {
          fieldPath: `${path}.offsetMs`,
          trackId: track.id,
        })
      }
    } else if (track.offsetMs !== undefined) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'offsetMs 必须与 afterTrack 一起使用。', {
        fieldPath: `${path}.offsetMs`,
        trackId: track.id,
      })
    }

    const endMs = startMs + durationMs
    if (endMs > MAX_MOTION_DURATION_MS) {
      throw new MotionError(
        MOTION_ERROR_SCHEMA_INVALID,
        `轨道结束时间超过 ${MAX_MOTION_DURATION_MS} 毫秒上限。`,
        { fieldPath: `${path}.durationMs`, trackId: track.id },
      )
    }
    compiled.startMs = startMs
    compiled.endMs = endMs
    compiledByIndex[index] = compiled
    compiling.delete(index)
    return { startMs, endMs, durationMs }
  }

  for (let index = 0; index < rawTracks.length; index += 1) {
    resolveStart(index)
  }

  // 自定义标签不得与其它轨道的 id 冲突；轨道 id 本身会自动登记为标签。
  for (const [label] of labels) {
    if (ids.has(label) && labels.get(label) !== label) {
      for (const [index, track] of rawTracks.entries()) {
        if (track.label === label) {
          throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `标签 ${label} 与其它轨道 id 冲突。`, {
            fieldPath: `timeline.tracks[${index}].label`,
            trackId: track.id,
          })
        }
      }
    }
  }

  const tracks = compiledByIndex
    .filter((track): track is CompiledMotionTrack => Boolean(track))
    .sort((left, right) => left.startMs - right.startMs || left.endMs - right.endMs || left.id.localeCompare(right.id))

  validateDomOwnership(tracks)
  validateExclusiveTargets(tracks)

  const requiredTracks = tracks.filter(track => track.required)
  const durationMs = requiredTracks.length > 0
    ? Math.max(...requiredTracks.map(track => track.endMs))
    : Math.max(...tracks.map(track => track.endMs))
  if (durationMs > MAX_MOTION_DURATION_MS) {
    throw new MotionError(
      MOTION_ERROR_SCHEMA_INVALID,
      `时间轴总时长超过 ${MAX_MOTION_DURATION_MS} 毫秒上限。`,
      { fieldPath: 'timeline.tracks' },
    )
  }

  const labelTimes: Record<string, number> = {}
  rawTracks.forEach((track, index) => {
    const compiled = compiledByIndex[index]
    if (!compiled) return
    labelTimes[track.id] = compiled.startMs
    if (track.label !== undefined) labelTimes[track.label] = compiled.startMs
  })
  const sortedLabels: Record<string, number> = {}
  for (const key of Object.keys(labelTimes).sort()) sortedLabels[key] = labelTimes[key]

  const posterTimeMs = resolvePosterTime(definition.poster, sortedLabels, durationMs)

  const body: Omit<CompiledMotionPlan, 'planDigest'> = {
    schemaVersion: MOTION_PLAN_SCHEMA_VERSION,
    timelineId,
    durationMs,
    posterTimeMs,
    primaryClockTrackId,
    requiredTrackIds: requiredTracks.map(track => track.id),
    labels: sortedLabels,
    tracks,
  }
  return {
    ...body,
    planDigest: digestMotionPayload(body),
  }
}

/** 判断编译结果是否包含可执行的主媒体时钟。 */
export function hasPrimaryClock(plan: CompiledMotionPlan): boolean {
  return plan.primaryClockTrackId !== null
}

/** 读取指定类型的轨道。 */
export function tracksOfType<T extends CompiledMotionTrack['type']>(
  plan: CompiledMotionPlan,
  type: T,
): Extract<CompiledMotionTrack, { type: T }>[] {
  return plan.tracks.filter((track): track is Extract<CompiledMotionTrack, { type: T }> => track.type === type)
}

/** 查找主媒体轨道；没有主时钟时返回 null。 */
export function primaryClockTrack(plan: CompiledMotionPlan): CompiledMediaTrack | null {
  if (!plan.primaryClockTrackId) return null
  const track = plan.tracks.find(item => item.id === plan.primaryClockTrackId)
  return track && track.type !== 'dom' && track.type !== 'model3d' ? track : null
}

const MOTION_ERROR_UNSUPPORTED_TYPE = 'TIMELINE_UNSUPPORTED' as const

function compileDomTrack(
  track: Extract<MotionTrackDefinition, { type: 'dom' }>,
  index: number,
  role: MotionTrackRole,
  required: boolean,
): CompiledDomTrack {
  const path = `timeline.tracks[${index}]`
  if (role === 'primary' || role === 'narration') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '主媒体与旁白角色只能用于音视频轨道。', {
      fieldPath: `${path}.role`,
      trackId: track.id,
    })
  }
  const target = requireString(track.target, `${path}.target`, MAX_SELECTOR_LENGTH)
  const durationMs = requireDuration(track.durationMs, `${path}.durationMs`, track.id)
  const preset = track.preset
  if (preset !== undefined && !(preset in PRESET_STATES)) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `不支持的 DOM 预设 ${String(preset)}。`, {
      fieldPath: `${path}.preset`,
      trackId: track.id,
    })
  }
  const presetState = preset ? PRESET_STATES[preset as DomMotionPreset] : undefined
  const from = resolveDomValues(normalizeDomState(track.from, `${path}.from`, track.id), presetState?.from)
  const to = resolveDomValues(normalizeDomState(track.to, `${path}.to`, track.id), presetState?.to)
  const properties = DOM_PROPERTIES.filter(property => from[property] !== undefined || to[property] !== undefined)
  if (properties.length === 0) {
    throw new MotionError(
      MOTION_ERROR_SCHEMA_INVALID,
      'DOM 轨道必须声明 preset 或至少一个 from/to 属性。',
      { fieldPath: `${path}.to`, trackId: track.id },
    )
  }
  return {
    type: 'dom',
    id: track.id,
    label: track.label ?? track.id,
    target,
    preset,
    from,
    to,
    properties,
    startMs: 0,
    endMs: 0,
    durationMs,
    required,
    role,
  }
}

function compileMediaTrack(
  track: Extract<MotionTrackDefinition, { type: MotionMediaType }>,
  index: number,
  role: MotionTrackRole,
  required: boolean,
  endBehavior: MotionEndBehavior,
): CompiledMediaTrack {
  const path = `timeline.tracks[${index}]`
  const asset = requireString(track.asset, `${path}.asset`, MAX_ASSET_NAME_LENGTH)
  const inMs = track.inMs === undefined ? 0 : requireNonNegative(track.inMs, `${path}.inMs`, track.id)
  const outMs = requirePositive(track.outMs, `${path}.outMs`, track.id)
  if (outMs <= inMs) {
    throw new MotionError(MOTION_ERROR_DURATION_UNRESOLVED, 'outMs 必须大于 inMs；未知资源时长不得用 0 代替。', {
      fieldPath: `${path}.outMs`,
      trackId: track.id,
    })
  }
  const rate = resolveRate(track.rate, `${path}.rate`, track.id)
  const repeat = resolveRepeat(track.repeat, `${path}.repeat`, track.id)
  const muted = track.muted === true
  const volume = track.volume === undefined ? 1 : requireUnitInterval(track.volume, `${path}.volume`, track.id)
  if (role === 'primary') {
    if (track.startMs !== undefined && track.startMs !== 0) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '主媒体必须从逻辑 0 开始。', {
        fieldPath: `${path}.startMs`,
        trackId: track.id,
      })
    }
    if (track.afterTrack !== undefined) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '主媒体不能依赖其它轨道起始。', {
        fieldPath: `${path}.afterTrack`,
        trackId: track.id,
      })
    }
    if (rate !== 1 || repeat !== 1) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '主媒体速率必须为 1 且只能播放一次。', {
        fieldPath: `${path}.rate`,
        trackId: track.id,
      })
    }
  }
  if (role === 'narration' && repeat !== 1) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '旁白轨道不允许重复。', {
      fieldPath: `${path}.repeat`,
      trackId: track.id,
    })
  }
  const durationMs = ((outMs - inMs) * repeat) / rate
  return {
    type: track.type,
    id: track.id,
    label: track.label ?? track.id,
    asset,
    selector: resolveOptionalString(track.selector, `${path}.selector`, MAX_SELECTOR_LENGTH),
    inMs,
    outMs,
    rate,
    repeat,
    muted,
    volume,
    endBehavior,
    startMs: 0,
    endMs: 0,
    durationMs,
    required,
    role,
    primary: role === 'primary',
  }
}

function compileModelTrack(
  track: Extract<MotionTrackDefinition, { type: 'model3d' }>,
  index: number,
  role: MotionTrackRole,
  required: boolean,
  endBehavior: MotionEndBehavior,
): CompiledModelTrack {
  const path = `timeline.tracks[${index}]`
  if (role === 'primary' || role === 'narration') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '主媒体与旁白角色只能用于音视频轨道。', {
      fieldPath: `${path}.role`,
      trackId: track.id,
    })
  }
  const asset = requireString(track.asset, `${path}.asset`, MAX_ASSET_NAME_LENGTH)
  const clip = normalizeClipReference(track.clip, `${path}.clip`, track.id)
  const inMs = track.inMs === undefined ? 0 : requireNonNegative(track.inMs, `${path}.inMs`, track.id)
  const outMs = track.outMs === undefined ? clip.durationMs : requirePositive(track.outMs, `${path}.outMs`, track.id)
  if (outMs > clip.durationMs) {
    throw new MotionError(MOTION_ERROR_DURATION_UNRESOLVED, '模型裁切终点超过片段真实时长。', {
      fieldPath: `${path}.outMs`,
      trackId: track.id,
    })
  }
  if (outMs <= inMs) {
    throw new MotionError(MOTION_ERROR_DURATION_UNRESOLVED, '模型 outMs 必须大于 inMs。', {
      fieldPath: `${path}.outMs`,
      trackId: track.id,
    })
  }
  const rate = resolveRate(track.rate, `${path}.rate`, track.id)
  const repeat = resolveRepeat(track.repeat, `${path}.repeat`, track.id)
  const transform = normalizeModelTransform(track.transform, `${path}.transform`, track.id)
  return {
    type: 'model3d',
    id: track.id,
    label: track.label ?? track.id,
    asset,
    selector: resolveOptionalString(track.selector, `${path}.selector`, MAX_ASSET_NAME_LENGTH),
    clip,
    inMs,
    outMs,
    rate,
    repeat,
    transform,
    endBehavior,
    startMs: 0,
    endMs: 0,
    durationMs: ((outMs - inMs) * repeat) / rate,
    required,
    role,
  }
}

function normalizeClipReference(
  value: ModelClipReference | undefined,
  path: string,
  trackId: string,
): ModelClipReference {
  if (!value || typeof value !== 'object') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '模型轨道必须声明 clip。', { fieldPath: path, trackId })
  }
  if (!Number.isInteger(value.index) || value.index < 0) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'clip.index 必须是非负整数。', {
      fieldPath: `${path}.index`,
      trackId,
    })
  }
  const durationMs = requirePositive(value.durationMs, `${path}.durationMs`, trackId)
  return {
    index: value.index,
    name: resolveOptionalString(value.name, `${path}.name`, 200),
    signature: resolveOptionalString(value.signature, `${path}.signature`, 200),
    durationMs,
  }
}

function normalizeModelTransform(
  value: Extract<MotionTrackDefinition, { type: 'model3d' }>['transform'],
  path: string,
  trackId: string,
): CompiledModelTrack['transform'] | undefined {
  if (value === undefined) return undefined
  if (!value || typeof value !== 'object') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'transform 必须是对象。', { fieldPath: path, trackId })
  }
  const from: ModelMotionTransformState = { ...MODEL_TRANSFORM_DEFAULTS, ...value.from }
  const to: ModelMotionTransformState = { ...MODEL_TRANSFORM_DEFAULTS, ...value.to }
  for (const [side, state] of [['from', from], ['to', to]] as const) {
    for (const key of Object.keys(MODEL_TRANSFORM_DEFAULTS) as Array<keyof ModelMotionTransformState>) {
      requireFiniteNumber(state[key], `${path}.${side}.${key}`, trackId)
    }
    if (state.scale! <= 0) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '模型整体缩放必须大于 0。', {
        fieldPath: `${path}.${side}.scale`,
        trackId,
      })
    }
  }
  return { from, to }
}

function normalizeDomState(
  value: DomMotionState | undefined,
  path: string,
  trackId: string,
): DomMotionState {
  if (value === undefined) return {}
  if (!value || typeof value !== 'object') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'DOM 状态必须是对象。', { fieldPath: path, trackId })
  }
  for (const property of Object.keys(value) as Array<keyof DomMotionState>) {
    if (!DOM_PROPERTIES.includes(property as DomMotionProperty)) {
      throw new MotionError(MOTION_ERROR_UNSUPPORTED_TYPE, `不支持的 DOM 属性 ${property}。`, {
        fieldPath: `${path}.${property}`,
        trackId,
      })
    }
    const numeric = requireFiniteNumber(value[property], `${path}.${property}`, trackId)
    if (property === 'opacity' && (numeric < 0 || numeric > 1)) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'opacity 必须在 0–1 之间。', {
        fieldPath: `${path}.${property}`,
        trackId,
      })
    }
    if (property === 'scale' && (numeric <= 0 || numeric > 10)) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'scale 必须在 (0,10] 之间。', {
        fieldPath: `${path}.${property}`,
        trackId,
      })
    }
    if ((property === 'x' || property === 'y' || property === 'rotation') && Math.abs(numeric) > MAX_ABSOLUTE_DOM_VALUE) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `${property} 超出允许范围。`, {
        fieldPath: `${path}.${property}`,
        trackId,
      })
    }
  }
  return { ...value }
}

function resolveDomValues(state: DomMotionState, preset: DomMotionState | undefined): DomMotionState {
  const merged = { ...preset, ...state }
  const result: DomMotionState = {}
  for (const property of DOM_PROPERTIES) {
    if (merged[property] !== undefined) result[property] = merged[property]
  }
  return result
}

function validateDomOwnership(tracks: CompiledMotionTrack[]): void {
  const domTracks = tracks.filter((track): track is CompiledDomTrack => track.type === 'dom')
  for (let leftIndex = 0; leftIndex < domTracks.length; leftIndex += 1) {
    const left = domTracks[leftIndex]
    for (let rightIndex = leftIndex + 1; rightIndex < domTracks.length; rightIndex += 1) {
      const right = domTracks[rightIndex]
      if (left.target !== right.target) continue
      if (!overlaps(left.startMs, left.endMs, right.startMs, right.endMs)) continue
      const conflict = left.properties.find(property => right.properties.includes(property))
      if (conflict) {
        throw new MotionError(
          MOTION_ERROR_PROPERTY_CONFLICT,
          `轨道 ${left.id} 与 ${right.id} 同时占用 ${left.target} 的 ${conflict} 属性。`,
          { fieldPath: `timeline.tracks.${right.id}.properties`, trackId: right.id },
        )
      }
    }
  }
}

function validateExclusiveTargets(tracks: CompiledMotionTrack[]): void {
  const claimed = new Map<string, string>()
  for (const track of tracks) {
    if (track.type === 'dom') continue
    const key = `${track.type}:${track.selector ?? track.asset}`
    const existing = claimed.get(key)
    if (existing) {
      throw new MotionError(
        MOTION_ERROR_PROPERTY_CONFLICT,
        `轨道 ${existing} 与 ${track.id} 同时占用同一媒体/模型目标。`,
        { fieldPath: `timeline.tracks.${track.id}.asset`, trackId: track.id },
      )
    }
    claimed.set(key, track.id)
  }
}

function resolvePosterTime(
  poster: PageTimelineDefinition['poster'],
  labels: Record<string, number>,
  durationMs: number,
): number {
  let timeMs = 0
  if (poster !== undefined) {
    if (!poster || typeof poster !== 'object') {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'poster 必须是对象。', { fieldPath: 'timeline.poster' })
    }
    if (poster.atMs !== undefined && poster.atLabel !== undefined) {
      throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'poster 的 atMs 与 atLabel 不能同时声明。', {
        fieldPath: 'timeline.poster',
      })
    }
    if (poster.atMs !== undefined) {
      timeMs = requireFiniteNumber(poster.atMs, 'timeline.poster.atMs')
    } else if (poster.atLabel !== undefined) {
      const label = requireString(poster.atLabel, 'timeline.poster.atLabel', 64)
      const labelTime = labels[label]
      if (labelTime === undefined) {
        throw new MotionError(MOTION_ERROR_TARGET_INVALID, `海报标签 ${label} 不存在。`, {
          fieldPath: 'timeline.poster.atLabel',
        })
      }
      timeMs = labelTime
    }
  }
  if (timeMs < 0 || timeMs > durationMs) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `海报时间必须在 0–${durationMs} 毫秒之间。`, {
      fieldPath: 'timeline.poster',
    })
  }
  return timeMs
}

function resolveRole(track: MotionTrackDefinition, path: string): MotionTrackRole {
  const role = track.role ?? 'content'
  if (!['primary', 'narration', 'content', 'decoration'].includes(role)) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `不支持的轨道角色 ${String(role)}。`, {
      fieldPath: `${path}.role`,
      trackId: track.id,
    })
  }
  return role
}

function resolveRequired(track: MotionTrackDefinition, role: MotionTrackRole): boolean {
  if (track.required === undefined) return role !== 'decoration'
  if (typeof track.required !== 'boolean') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'required 必须是布尔值。', {
      fieldPath: `timeline.tracks.${track.id}.required`,
      trackId: track.id,
    })
  }
  return track.required
}

function resolveEndBehavior(track: MotionTrackDefinition, path: string): MotionEndBehavior {
  if (track.type === 'dom') return 'hold'
  const value = track.endBehavior ?? 'hold'
  if (value !== 'hold' && value !== 'restore') {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, 'endBehavior 只能是 hold 或 restore。', {
      fieldPath: `${path}.endBehavior`,
      trackId: track.id,
    })
  }
  return value
}

function resolveRate(value: number | undefined, path: string, trackId: string): number {
  if (value === undefined) return 1
  const rate = requireFiniteNumber(value, path, trackId)
  if (rate < MIN_RATE || rate > MAX_RATE) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `rate 必须在 ${MIN_RATE}–${MAX_RATE} 之间。`, {
      fieldPath: path,
      trackId,
    })
  }
  return rate
}

function resolveRepeat(value: number | undefined, path: string, trackId: string): number {
  if (value === undefined) return 1
  if (!Number.isInteger(value) || value < 1 || value > MAX_MOTION_REPEAT) {
    throw new MotionError(
      MOTION_ERROR_SCHEMA_INVALID,
      `repeat 必须是 1–${MAX_MOTION_REPEAT} 的整数；无限装饰不参与首期完成判定。`,
      { fieldPath: path, trackId },
    )
  }
  return value
}

function requireString(value: unknown, path: string, maxLength: number): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '字段必须是非空字符串。', { fieldPath: path })
  }
  const text = value.trim()
  if (text.length > maxLength) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `字段长度超过 ${maxLength}。`, { fieldPath: path })
  }
  return text
}

function resolveOptionalString(value: unknown, path: string, maxLength: number): string | undefined {
  if (value === undefined || value === null) return undefined
  return requireString(value, path, maxLength)
}

function requireNumber(value: unknown, path: string, trackId?: string): number {
  return requireFiniteNumber(value, path, trackId)
}

function requireFiniteNumber(value: unknown, path: string, trackId?: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '字段必须是有限数值。', { fieldPath: path, trackId })
  }
  return value
}

function requirePositive(value: unknown, path: string, trackId?: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new MotionError(MOTION_ERROR_DURATION_UNRESOLVED, '字段必须是有限正数。', { fieldPath: path, trackId })
  }
  return value
}

function requireNonNegative(value: unknown, path: string, trackId?: string): number {
  const numeric = requireFiniteNumber(value, path, trackId)
  if (numeric < 0) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '字段不得小于 0。', { fieldPath: path, trackId })
  }
  return numeric
}

function requireUnitInterval(value: unknown, path: string, trackId?: string): number {
  const numeric = requireFiniteNumber(value, path, trackId)
  if (numeric < 0 || numeric > 1) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, '字段必须在 0–1 之间。', { fieldPath: path, trackId })
  }
  return numeric
}

function requireDuration(value: unknown, path: string, trackId: string): number {
  const numeric = requirePositive(value, path, trackId)
  if (numeric > MAX_MOTION_DURATION_MS) {
    throw new MotionError(MOTION_ERROR_SCHEMA_INVALID, `轨道时长超过 ${MAX_MOTION_DURATION_MS} 毫秒上限。`, {
      fieldPath: path,
      trackId,
    })
  }
  return numeric
}

function overlaps(leftStart: number, leftEnd: number, rightStart: number, rightEnd: number): boolean {
  return leftStart < rightEnd && rightStart < leftEnd
}

/**
 * 对任意可序列化值做稳定序列化：对象键排序、数组保持顺序。
 * 用于 planDigest 与状态证明，不用于安全签名。
 */
export function stableMotionStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value) ?? 'null'
  }
  if (Array.isArray(value)) {
    return `[${value.map(item => stableMotionStringify(item)).join(',')}]`
  }
  const record = value as Record<string, unknown>
  const keys = Object.keys(record).sort()
  return `{${keys.map(key => `${JSON.stringify(key)}:${stableMotionStringify(record[key])}`).join(',')}}`
}

/**
 * 计算稳定的 64 位十六进制摘要（双 FNV-1a 32 位），仅用于内容身份与缓存分区。
 */
export function digestMotionPayload(value: unknown): string {
  const text = stableMotionStringify(value)
  return `${fnv1a32(text, 0x811c9dc5)}${fnv1a32(text, 0x9e3779b9)}`
}

function fnv1a32(input: string, seed: number): string {
  let hash = seed >>> 0
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

/** 把未知错误转为保留定位的 MotionError；供编译入口与适配器共享。 */
export function normalizeMotionFailure(error: unknown): MotionError {
  return toMotionError(error)
}
