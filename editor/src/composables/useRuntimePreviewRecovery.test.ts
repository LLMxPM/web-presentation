/** 文件功能：验证预览恢复预算、可见性检查、并发去重和切换目标的失效隔离。 */
import { defineComponent, h, nextTick, ref } from 'vue'
import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { previewTokenExpiresAt, useRuntimePreviewRecovery } from './useRuntimePreviewRecovery'
import { renewPreviewArtifactAccess } from '@/api/preview'

vi.mock('@/api/preview', () => ({
  renewPreviewArtifactAccess: vi.fn(),
}))

afterEach(() => vi.restoreAllMocks())

describe('预览自动恢复', () => {
  it('替换 artifact URL 不得重置失败链预算，成功或手动重试才开启新周期', async () => {
    const host = mountRecovery()
    expect(host.recovery.tryRecover('PREVIEW_CONTEXT_INVALID')).toBe(true)
    host.frameUrl.value = 'https://backend.example/preview/artifacts/new?token=new'
    expect(host.recovery.tryRecover('ARTIFACT_NOT_FOUND')).toBe(false)
    await nextTick()
    expect(host.recover).toHaveBeenCalledTimes(1)
    host.recovery.reset()
    expect(host.recovery.tryRecover('ARTIFACT_NOT_FOUND')).toBe(true)
    await nextTick()
    expect(host.recover).toHaveBeenCalledTimes(2)
  })

  it('不会重试权限、版本或服务错误，切换目标使排队中的旧恢复失效', async () => {
    const host = mountRecovery()
    expect(host.recovery.tryRecover('PREVIEW_ARTIFACT_MISMATCH')).toBe(false)
    expect(host.recovery.tryRecover('PREVIEW_VERSION_SKEW')).toBe(false)
    expect(host.recovery.tryRecover('RUNTIME_PREVIEW_UNAVAILABLE')).toBe(false)
    expect(host.recovery.tryRecover('PREVIEW_CONTEXT_INVALID')).toBe(true)
    host.sourceKey.value = 'page-2'
    await nextTick()
    expect(host.recover).not.toHaveBeenCalled()
    expect(host.recovery.tryRecover('PREVIEW_CONTEXT_INVALID')).toBe(true)
  })

  it('标签页激活依据真实 exp 只刷新已过期票据，不把隐藏或有效预览重建', async () => {
    const host = mountRecovery()
    const visibility = vi.spyOn(document, 'visibilityState', 'get')
    host.frameUrl.value = previewUrl(Math.floor(Date.now() / 1000) + 600)
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(host.recover).not.toHaveBeenCalled()
    host.frameUrl.value = previewUrl(Math.floor(Date.now() / 1000) - 1)
    visibility.mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(host.recover).not.toHaveBeenCalled()
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(host.recover).toHaveBeenCalledTimes(1)
  })

  it('票据缺失、非法或 exp 类型错误时不推断固定一小时有效期', () => {
    expect(previewTokenExpiresAt('broken')).toBeNull()
    expect(previewTokenExpiresAt('https://backend.example/?token=invalid')).toBeNull()
    expect(previewTokenExpiresAt(previewUrl('3600'))).toBeNull()
    expect(previewTokenExpiresAt(previewUrl(3600))).toBe(3600000)
  })

  it('票据即将到期时优先调用 renewPreviewArtifactAccess 续签，成功更新 URL 且不全量重建', async () => {
    vi.mocked(renewPreviewArtifactAccess).mockResolvedValueOnce({
      preview_url: 'https://backend.example/preview/artifacts/art-renewed?token=renewed',
      token: 'renewed',
      expires_at: '2026-10-16T12:00:00Z',
      artifact_id: 'art-test-100',
    })

    const onRenewed = vi.fn()
    const recover = vi.fn()
    const frameUrl = ref(previewUrl(Math.floor(Date.now() / 1000) + 10))
    const sourceKey = ref('page-1')
    const artifactId = ref('art-test-100')

    let recovery!: ReturnType<typeof useRuntimePreviewRecovery>
    render(defineComponent({
      setup() {
        recovery = useRuntimePreviewRecovery({
          frameUrl: () => frameUrl.value,
          sourceKey: () => sourceKey.value,
          artifactId: () => artifactId.value,
          onRenewed,
          recover,
        })
        return () => h('div')
      },
    }))

    await recovery.executeRenewOrRecover()
    await nextTick()

    expect(renewPreviewArtifactAccess).toHaveBeenCalledWith('art-test-100')
    expect(onRenewed).toHaveBeenCalledWith('https://backend.example/preview/artifacts/art-renewed?token=renewed')
    expect(recover).not.toHaveBeenCalled()
  })

  it('续签失败（如 artifact 410 过期）时自动降级回退至 recover 全量重建', async () => {
    vi.mocked(renewPreviewArtifactAccess).mockRejectedValueOnce(new Error('PREVIEW_ARTIFACT_EXPIRED'))

    const onRenewed = vi.fn()
    const recover = vi.fn()
    const frameUrl = ref(previewUrl(Math.floor(Date.now() / 1000) + 10))
    const sourceKey = ref('page-1')
    const artifactId = ref('art-expired-200')

    let recovery!: ReturnType<typeof useRuntimePreviewRecovery>
    render(defineComponent({
      setup() {
        recovery = useRuntimePreviewRecovery({
          frameUrl: () => frameUrl.value,
          sourceKey: () => sourceKey.value,
          artifactId: () => artifactId.value,
          onRenewed,
          recover,
        })
        return () => h('div')
      },
    }))

    await recovery.executeRenewOrRecover()
    await nextTick()

    expect(renewPreviewArtifactAccess).toHaveBeenCalledWith('art-expired-200')
    expect(onRenewed).not.toHaveBeenCalled()
    expect(recover).toHaveBeenCalledTimes(1)
  })
})

/** 挂载恢复生命周期，便于验证真实 DOM 事件订阅与卸载。 */
function mountRecovery() {
  const frameUrl = ref('https://backend.example/preview/artifacts/original')
  const sourceKey = ref('page-1')
  const recover = vi.fn()
  let recovery!: ReturnType<typeof useRuntimePreviewRecovery>
  render(defineComponent({
    setup() {
      recovery = useRuntimePreviewRecovery({ frameUrl: () => frameUrl.value, sourceKey: () => sourceKey.value, recover })
      return () => h('div')
    },
  }))
  return { frameUrl, sourceKey, recover, recovery }
}

/** 构造仅用于客户端过期提示测试的 JWT，不作为认证凭据。 */
function previewUrl(exp: unknown): string {
  return `https://backend.example/preview/artifacts/rt_1?token=head.${btoa(JSON.stringify({ exp }))}.signature`
}
