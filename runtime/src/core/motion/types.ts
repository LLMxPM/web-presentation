/**
 * 文件功能：定义 page-timeline.v1 创作定义、规范计划与运行快照的共享类型。
 *
 * 字段事实源位于本文件与作者文档 authoring-contract.md；编译器只做归一化、
 * 校验和确定性排序，不读取 DOM、不播放媒体、不执行视觉函数。
 */

/** 创作定义结构版本；不兼容演进时新增 v2，不原地改写 v1 语义。 */
export const PAGE_TIMELINE_SCHEMA_VERSION = 1

/** 编译后规范计划版本；进入诊断与截图身份。 */
export const MOTION_PLAN_SCHEMA_VERSION = 1

/** 单个时间轴允许的轨道上限。 */
export const MAX_MOTION_TRACKS = 128
/** 有限轨道总时长上限（1 小时），防止误写超大时间。 */
export const MAX_MOTION_DURATION_MS = 3_600_000
/** 单次裁切/重复后的轨道时长上限，与总时长一致。 */
export const MAX_MOTION_REPEAT = 1_000

export type MotionTrackType = 'dom' | 'audio' | 'video' | 'model3d'
export type MotionMediaType = Extract<MotionTrackType, 'audio' | 'video'>
export type MotionVisualMode = 'full' | 'reduced'
export type MotionTrackRole = 'primary' | 'narration' | 'content' | 'decoration'
export type MotionEndBehavior = 'hold' | 'restore'
export type DomMotionPreset = 'fade' | 'fade-up' | 'scale-in'

/** DOM 动效可声明属性；首期只支持这一组受控属性。 */
export type DomMotionProperty = 'opacity' | 'x' | 'y' | 'scale' | 'rotation'

/** DOM 视觉状态；未声明属性采用元素当前样式或预设初态。 */
export interface DomMotionState {
  opacity?: number
  x?: number
  y?: number
  scale?: number
  rotation?: number
}

/** 模型整体包装变换；不修改片段内部骨骼与节点动画。 */
export interface ModelMotionTransformState {
  x?: number
  y?: number
  z?: number
  scale?: number
  /** 绕 Y 轴旋转角（度）。 */
  rotationY?: number
}

export interface MotionTrackTiming {
  /** 绝对起点（毫秒）；与 afterTrack 互斥。 */
  startMs?: number
  /** 命名前驱轨道；起点 = 前驱结束 + offsetMs。 */
  afterTrack?: string
  /** 相对前驱结束的偏移（毫秒），可为负值但结果起点不得小于 0。 */
  offsetMs?: number
}

interface MotionTrackBase extends MotionTrackTiming {
  /** 稳定轨道 id，同时作为默认标签。 */
  id: string
  /** 自定义标签；不得与其它轨道 id 或标签重名。 */
  label?: string
  /** 是否参与完成判定与总时长；decoration 默认 false。 */
  required?: boolean
  /** 轨道用途；媒体用于主时钟、旁白与静音约束。 */
  role?: MotionTrackRole
}

export interface DomMotionTrackDefinition extends MotionTrackBase {
  type: 'dom'
  /** 页面作用域内的 CSS 选择器。 */
  target: string
  preset?: DomMotionPreset
  from?: DomMotionState
  to?: DomMotionState
  /** 动效时长（毫秒）；必须为有限正数。 */
  durationMs: number
}

export interface MediaMotionTrackDefinition extends MotionTrackBase {
  type: MotionMediaType
  /** 资源逻辑名 asset.name；由实际 AssetAudio/AssetVideo 渲染。 */
  asset: string
  /** 可选元素选择器；缺省按资源名定位。 */
  selector?: string
  /** 裁切起点（毫秒），默认 0。 */
  inMs?: number
  /** 裁切终点（毫秒）；必须显式提供，不从资源猜测。 */
  outMs: number
  /** 播放速率，默认 1。 */
  rate?: number
  /** 有限重复次数，默认 1；主媒体与旁白只能为 1。 */
  repeat?: number
  /** 是否静音；同步辅助视频必须声明为 true。 */
  muted?: boolean
  /** 音量 0–1，默认 1。 */
  volume?: number
  endBehavior?: MotionEndBehavior
}

export interface ModelClipReference {
  /** 资源内动画索引。 */
  index: number
  /** 动画名称，仅作辅助校验。 */
  name?: string
  /** 后端动作语义签名；为空时仍按索引校验。 */
  signature?: string
  /** 片段真实时长（毫秒），必须来自资源查询，不由编译器猜测。 */
  durationMs: number
}

export interface ModelMotionTrackDefinition extends MotionTrackBase {
  type: 'model3d'
  /** 资源逻辑名 asset.name。 */
  asset: string
  /** 可选模型根选择器；缺省按资源名定位。 */
  selector?: string
  clip: ModelClipReference
  /** 片段裁切起点（毫秒），默认 0。 */
  inMs?: number
  /** 片段裁切终点（毫秒），默认 clip.durationMs。 */
  outMs?: number
  rate?: number
  repeat?: number
  /** 整体包装变换轨道；与片段内部动画并行。 */
  transform?: {
    from?: ModelMotionTransformState
    to?: ModelMotionTransformState
  }
  endBehavior?: MotionEndBehavior
}

export type MotionTrackDefinition =
  | DomMotionTrackDefinition
  | MediaMotionTrackDefinition
  | ModelMotionTrackDefinition

export interface MotionPosterDefinition {
  atMs?: number
  atLabel?: string
}

export interface PageTimelineDefinition {
  schemaVersion: typeof PAGE_TIMELINE_SCHEMA_VERSION
  timelineId: string
  tracks: MotionTrackDefinition[]
  /** 默认海报位置；缺省为 0。atMs 与 atLabel 互斥。 */
  poster?: MotionPosterDefinition
}

export interface CompiledDomTrack {
  type: 'dom'
  id: string
  label: string
  target: string
  preset?: DomMotionPreset
  from: DomMotionState
  to: DomMotionState
  properties: DomMotionProperty[]
  startMs: number
  endMs: number
  durationMs: number
  required: boolean
  role: MotionTrackRole
}

export interface CompiledMediaTrack {
  type: MotionMediaType
  id: string
  label: string
  asset: string
  selector?: string
  inMs: number
  outMs: number
  rate: number
  repeat: number
  muted: boolean
  volume: number
  endBehavior: MotionEndBehavior
  startMs: number
  endMs: number
  durationMs: number
  required: boolean
  role: MotionTrackRole
  primary: boolean
}

export interface CompiledModelTrack {
  type: 'model3d'
  id: string
  label: string
  asset: string
  selector?: string
  clip: ModelClipReference
  inMs: number
  outMs: number
  rate: number
  repeat: number
  transform?: {
    from: ModelMotionTransformState
    to: ModelMotionTransformState
  }
  endBehavior: MotionEndBehavior
  startMs: number
  endMs: number
  durationMs: number
  required: boolean
  role: MotionTrackRole
}

export type CompiledMotionTrack = CompiledDomTrack | CompiledMediaTrack | CompiledModelTrack

export interface CompiledMotionPlan {
  schemaVersion: typeof MOTION_PLAN_SCHEMA_VERSION
  timelineId: string
  planDigest: string
  durationMs: number
  posterTimeMs: number
  primaryClockTrackId: string | null
  requiredTrackIds: string[]
  labels: Record<string, number>
  tracks: CompiledMotionTrack[]
  /** Runtime 拥有的原生视觉段落；只保存规范身份，不序列化作者函数或元素。 */
  visual?: { durationMs: number; digest: string; labels: Record<string, number> }
}

export type MotionPlaybackIntent = 'stopped' | 'playing' | 'paused'

export type MotionRunPhase =
  | 'idle'
  | 'preparing'
  | 'ready'
  | 'seeking'
  | 'buffering'
  | 'blocked'
  | 'completed'
  | 'error'
  | 'disposed'

export interface MotionStateProof {
  trackId: string
  type: MotionTrackType
  positionMs: number
  /** 采样与固化结果的稳定摘要；同一计划同一位置应稳定。 */
  digest: string
  details?: Record<string, unknown>
}

export interface MotionTransportSnapshot {
  timelineId: string
  planDigest: string
  pagePath: string
  generation: number
  intent: MotionPlaybackIntent
  phase: MotionRunPhase
  positionMs: number
  durationMs: number
  revision: number
  completedTrackIds: string[]
  errorCode: string | null
  errorMessage: string
}
