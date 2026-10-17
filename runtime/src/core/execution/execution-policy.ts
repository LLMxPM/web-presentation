/**
 * 文件功能：定义 Runtime 执行上下文与策略优先级。
 * 执行策略在宿主初始化前解析，捕获/导出/缩略图等静态上下文高于项目配置，
 * 不允许被嵌套宿主放宽。本模块不依赖 Vue 或 DOM，便于确定性测试。
 */
import type { RuntimePreviewContext } from '@/core/shared/runtime-preview'

export type ExecutionContextKind =
  | 'presentation'
  | 'interactive-preview'
  | 'thumbnail'
  | 'capture'
  | 'export'

export type MediaPlaybackMode = 'allow' | 'gesture' | 'block'

export interface ExecutionPolicy {
  kind: ExecutionContextKind
  allowAutoStart: boolean
  allowAutoAdvance: boolean
  allowPresenterSync: boolean
  allowMediaPlayback: boolean
  allowAutoplay: boolean
}

/**
 * 各上下文的基准策略。
 * - presentation：主画布/观众窗口，允许后续接入自动开始与媒体播放。
 * - interactive-preview：单页/组件/资源预览，禁止自动开始与自动翻页，媒体只允许用户手势触发。
 * - thumbnail：缩略图、演讲者小窗、卡片，禁止自动推进与任何媒体播放。
 * - capture/export：截图与导出，全部禁用以保证静态结果。
 */
export const EXECUTION_POLICIES: Record<ExecutionContextKind, ExecutionPolicy> = {
  presentation: { kind: 'presentation', allowAutoStart: true, allowAutoAdvance: true, allowPresenterSync: true, allowMediaPlayback: true, allowAutoplay: true },
  'interactive-preview': { kind: 'interactive-preview', allowAutoStart: false, allowAutoAdvance: false, allowPresenterSync: false, allowMediaPlayback: true, allowAutoplay: false },
  thumbnail: { kind: 'thumbnail', allowAutoStart: false, allowAutoAdvance: false, allowPresenterSync: false, allowMediaPlayback: false, allowAutoplay: false },
  capture: { kind: 'capture', allowAutoStart: false, allowAutoAdvance: false, allowPresenterSync: false, allowMediaPlayback: false, allowAutoplay: false },
  export: { kind: 'export', allowAutoStart: false, allowAutoAdvance: false, allowPresenterSync: false, allowMediaPlayback: false, allowAutoplay: false },
}

const KIND_RANK: Record<ExecutionContextKind, number> = {
  presentation: 0,
  'interactive-preview': 1,
  thumbnail: 2,
  capture: 3,
  export: 3,
}

export interface ExecutionContextInput {
  search?: string
  previewContext?: Pick<RuntimePreviewContext, 'previewKind' | 'entryDescriptor'> | null
}

/**
 * 解析本次宿主初始化使用的执行上下文。
 * 优先级：内部显式 runtimeExecution > runtimeCapture > 非项目预览入口 > runtimeMode > 普通主画布。
 * 忽略 channel 等演讲同步参数，捕获页面不能从频道恢复放映状态。
 */
export function resolveExecutionContext(input: ExecutionContextInput = {}): ExecutionPolicy {
  const query = new URLSearchParams(input.search ?? '')
  const explicit = query.get('runtimeExecution')
  if (isExecutionContextKind(explicit)) return EXECUTION_POLICIES[explicit]
  if (query.get('runtimeCapture') === '1') return EXECUTION_POLICIES.capture

  const preview = input.previewContext
  if (preview && (preview.previewKind !== 'project' || preview.entryDescriptor?.entry_type === 'module')) {
    return EXECUTION_POLICIES['interactive-preview']
  }

  const mode = query.get('runtimeMode')
  if (mode === 'cards' || mode === 'presenter') return EXECUTION_POLICIES['interactive-preview']
  return EXECUTION_POLICIES.presentation
}

export function isExecutionContextKind(value: unknown): value is ExecutionContextKind {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(EXECUTION_POLICIES, value)
}

/**
 * 以父级策略为上限收紧子宿主策略。
 * 任何嵌套宿主都不能把静态上下文重新放宽为可自动播放。
 */
export function mergeExecutionPolicies(parent: ExecutionPolicy, child: ExecutionPolicy): ExecutionPolicy {
  return {
    kind: KIND_RANK[child.kind] > KIND_RANK[parent.kind] ? child.kind : parent.kind,
    allowAutoStart: parent.allowAutoStart && child.allowAutoStart,
    allowAutoAdvance: parent.allowAutoAdvance && child.allowAutoAdvance,
    allowPresenterSync: parent.allowPresenterSync && child.allowPresenterSync,
    allowMediaPlayback: parent.allowMediaPlayback && child.allowMediaPlayback,
    allowAutoplay: parent.allowAutoplay && child.allowAutoplay,
  }
}

/** 项目/页面配置的 auto_start 只有执行策略同时允许时才生效。 */
export function shouldStartAutomatically(policy: ExecutionPolicy, configuredAutoStart: boolean): boolean {
  return Boolean(configuredAutoStart && policy.allowAutoStart)
}

/** 自动翻页只在允许自动推进的上下文生效。 */
export function shouldAdvanceAutomatically(policy: ExecutionPolicy): boolean {
  return policy.allowAutoAdvance
}

/** 将策略映射为媒体守卫可执行的三档模式。 */
export function mediaPlaybackMode(policy: ExecutionPolicy): MediaPlaybackMode {
  if (!policy.allowMediaPlayback) return 'block'
  return policy.allowAutoplay ? 'allow' : 'gesture'
}
