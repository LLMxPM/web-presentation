/** 文件功能：验证执行上下文解析优先级、静态上下文收紧与自动策略判定。 */
import { describe, expect, it } from 'vitest'
import type { RuntimePreviewContext } from '@/core/shared/runtime-preview'
import {
  EXECUTION_POLICIES,
  mediaPlaybackMode,
  mergeExecutionPolicies,
  resolveExecutionContext,
  shouldAdvanceAutomatically,
  shouldStartAutomatically,
} from './execution-policy'

function preview(overrides: Partial<RuntimePreviewContext> = {}): Pick<RuntimePreviewContext, 'previewKind' | 'entryDescriptor'> {
  return {
    previewKind: 'project',
    entryDescriptor: { entry_type: 'route', route: '/home' },
    ...overrides,
  }
}

describe('resolveExecutionContext', () => {
  it('普通主画布与观众窗口保持 presentation', () => {
    expect(resolveExecutionContext().kind).toBe('presentation')
    expect(resolveExecutionContext({ search: '?runtimeMode=normal' }).kind).toBe('presentation')
    expect(resolveExecutionContext({ search: '?runtimeMode=display' }).kind).toBe('presentation')
  })

  it('捕获上下文优先于模式、预览与频道参数', () => {
    const policy = resolveExecutionContext({
      search: '?runtimeCapture=1&runtimeMode=presenter&channel=abc&runtimeCaptureTicket=req_1',
      previewContext: preview(),
    })
    expect(policy).toEqual(EXECUTION_POLICIES.capture)
    expect(policy.allowAutoStart).toBe(false)
    expect(policy.allowMediaPlayback).toBe(false)
  })

  it('内部显式执行上下文优先级最高', () => {
    expect(resolveExecutionContext({ search: '?runtimeExecution=export&runtimeCapture=1' }).kind).toBe('export')
    expect(resolveExecutionContext({ search: '?runtimeExecution=thumbnail&runtimeMode=display' }).kind).toBe('thumbnail')
    expect(resolveExecutionContext({ search: '?runtimeExecution=unknown&runtimeMode=cards' }).kind).toBe('interactive-preview')
  })

  it('单页、组件和资源预览默认禁用自动开始与自动翻页', () => {
    expect(resolveExecutionContext({ previewContext: preview({ previewKind: 'page' }) }).kind).toBe('interactive-preview')
    expect(resolveExecutionContext({ previewContext: preview({ previewKind: 'component' }) }).kind).toBe('interactive-preview')
    expect(resolveExecutionContext({ previewContext: preview({ previewKind: 'asset' }) }).kind).toBe('interactive-preview')
    expect(resolveExecutionContext({
      previewContext: preview({ entryDescriptor: { entry_type: 'module', module_path: 'src/views/a.vue' } }),
    }).kind).toBe('interactive-preview')
    expect(resolveExecutionContext({ previewContext: preview() }).kind).toBe('presentation')
  })

  it('卡片与演讲者控制台不是主放映画布', () => {
    expect(resolveExecutionContext({ search: '?runtimeMode=cards' }).kind).toBe('interactive-preview')
    expect(resolveExecutionContext({ search: '?runtimeMode=presenter' }).kind).toBe('interactive-preview')
  })
})

describe('执行策略判定', () => {
  it('静态上下文禁止自动开始、自动翻页、同步与媒体播放', () => {
    for (const policy of [EXECUTION_POLICIES.capture, EXECUTION_POLICIES.export, EXECUTION_POLICIES.thumbnail]) {
      expect(shouldStartAutomatically(policy, true)).toBe(false)
      expect(shouldAdvanceAutomatically(policy)).toBe(false)
      expect(policy.allowPresenterSync).toBe(false)
      expect(mediaPlaybackMode(policy)).toBe('block')
    }
  })

  it('交互预览允许手势播放但禁止自动开始与自动播放', () => {
    const policy = EXECUTION_POLICIES['interactive-preview']
    expect(shouldStartAutomatically(policy, true)).toBe(false)
    expect(shouldAdvanceAutomatically(policy)).toBe(false)
    expect(mediaPlaybackMode(policy)).toBe('gesture')
  })

  it('只有 presentation 允许项目 auto_start 生效', () => {
    expect(shouldStartAutomatically(EXECUTION_POLICIES.presentation, true)).toBe(true)
    expect(shouldStartAutomatically(EXECUTION_POLICIES.presentation, false)).toBe(false)
    expect(mediaPlaybackMode(EXECUTION_POLICIES.presentation)).toBe('allow')
  })

  it('嵌套作用域只能收紧，不能把捕获/缩略图放宽', () => {
    const thumbnailInsidePresentation = mergeExecutionPolicies(EXECUTION_POLICIES.presentation, EXECUTION_POLICIES.thumbnail)
    expect(thumbnailInsidePresentation).toMatchObject({
      kind: 'thumbnail',
      allowAutoStart: false,
      allowAutoAdvance: false,
      allowPresenterSync: false,
      allowMediaPlayback: false,
      allowAutoplay: false,
    })

    const presentationInsideCapture = mergeExecutionPolicies(EXECUTION_POLICIES.capture, EXECUTION_POLICIES.presentation)
    expect(presentationInsideCapture.kind).toBe('capture')
    expect(presentationInsideCapture.allowAutoStart).toBe(false)
    expect(mediaPlaybackMode(presentationInsideCapture)).toBe('block')

    const interactiveInsidePresentation = mergeExecutionPolicies(EXECUTION_POLICIES.presentation, EXECUTION_POLICIES['interactive-preview'])
    expect(interactiveInsidePresentation.kind).toBe('interactive-preview')
    expect(mediaPlaybackMode(interactiveInsidePresentation)).toBe('gesture')
  })
})
