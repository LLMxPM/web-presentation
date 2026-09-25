/**
 * 文件用途：验证预览有界缓存的容量淘汰、TTL 过期、artifact 失效与稳定内容身份键。
 */

import { describe, expect, it } from 'vitest'

import {
  buildPreviewCacheKey,
  PreviewBoundedCache,
  PREVIEW_CACHE_IDENTITY_MANIFEST,
  PREVIEW_CACHE_IDENTITY_PREVIEW_TOKEN,
  PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN,
} from './runtime-preview-cache'

/** 可手动推进的测试时钟。 */
function createClock(startMs = 0) {
  let current = startMs
  return {
    now: () => current,
    advance(ms: number) {
      current += ms
    },
  }
}

describe('PreviewBoundedCache', () => {
  it('超出容量时应按 LRU 淘汰最久未使用条目', () => {
    const cache = new PreviewBoundedCache<string>({ maxEntries: 2, ttlMs: 60_000 })

    cache.set('k1', 'v1', { artifactId: 'a1' })
    cache.set('k2', 'v2', { artifactId: 'a2' })
    // 访问 k1 使其成为最近使用，k2 变为最久未使用
    expect(cache.get('k1')).toBe('v1')
    cache.set('k3', 'v3', { artifactId: 'a3' })

    expect(cache.get('k1')).toBe('v1')
    expect(cache.get('k2')).toBeUndefined()
    expect(cache.get('k3')).toBe('v3')
    expect(cache.size).toBe(2)
  })

  it('条目超过 TTL 后应过期不可读', () => {
    const clock = createClock(1_000)
    const cache = new PreviewBoundedCache<string>({ maxEntries: 10, ttlMs: 5_000, now: clock.now })

    cache.set('k1', 'v1', { artifactId: 'a1' })
    expect(cache.get('k1')).toBe('v1')

    clock.advance(4_999)
    expect(cache.get('k1')).toBe('v1')

    clock.advance(2)
    expect(cache.get('k1')).toBeUndefined()
    expect(cache.size).toBe(0)
  })

  it('写入时可指定更短的条目级 TTL', () => {
    const clock = createClock(0)
    const cache = new PreviewBoundedCache<string>({ maxEntries: 10, ttlMs: 60_000, now: clock.now })

    cache.set('k1', 'v1', { artifactId: 'a1', ttlMs: 1_000 })
    clock.advance(1_001)
    expect(cache.get('k1')).toBeUndefined()
  })

  it('invalidateArtifact 应只清理指定 artifact 的条目', () => {
    const cache = new PreviewBoundedCache<string>({ maxEntries: 10, ttlMs: 60_000 })
    cache.set('a1::m', 'manifest-a1', { artifactId: 'a1' })
    cache.set('a1::t', 'css-a1', { artifactId: 'a1' })
    cache.set('a2::m', 'manifest-a2', { artifactId: 'a2' })

    const removed = cache.invalidateArtifact('a1')

    expect(removed).toBe(2)
    expect(cache.get('a1::m')).toBeUndefined()
    expect(cache.get('a1::t')).toBeUndefined()
    expect(cache.get('a2::m')).toBe('manifest-a2')
    expect(cache.size).toBe(1)
  })

  it('容量淘汰发生在写入时，且命中会刷新 LRU 位置', () => {
    const cache = new PreviewBoundedCache<number>({ maxEntries: 3, ttlMs: 60_000 })
    cache.set('k1', 1, { artifactId: 'a' })
    cache.set('k2', 2, { artifactId: 'a' })
    cache.set('k3', 3, { artifactId: 'a' })

    // k1 被访问后变为最近使用
    expect(cache.get('k1')).toBe(1)
    cache.set('k4', 4, { artifactId: 'a' })

    expect(cache.get('k2')).toBeUndefined()
    expect(cache.get('k1')).toBe(1)
    expect(cache.get('k3')).toBe(3)
    expect(cache.get('k4')).toBe(4)
  })
})

describe('buildPreviewCacheKey 内容身份', () => {
  it('键只由 artifact_id 与内容身份构成，与短期 token 无关', () => {
    const key1 = buildPreviewCacheKey('artifact-1', PREVIEW_CACHE_IDENTITY_MANIFEST)
    const key2 = buildPreviewCacheKey('artifact-1', PREVIEW_CACHE_IDENTITY_MANIFEST)

    expect(key1).toBe(key2)
    expect(key1).toContain('artifact-1')
    expect(key1).not.toContain('token')
  })

  it('换票（preview / service token 轮换）不产生新的计算缓存身份', () => {
    const artifactId = 'artifact-1'
    // 同一内容身份在不同 token 场景下键保持稳定
    const manifestKeyBefore = buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_MANIFEST)
    const tailwindKeyBefore = buildPreviewCacheKey(artifactId, 'source-signature-hash')

    // 模拟换票：token 值变化，但 token 不参与键构造
    const previewTokenA = 'preview-token-aaa'
    const previewTokenB = 'preview-token-bbb'
    const serviceTokenA = 'service-token-aaa'
    const serviceTokenB = 'service-token-bbb'

    const manifestKeyAfter = buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_MANIFEST)
    const tailwindKeyAfter = buildPreviewCacheKey(artifactId, 'source-signature-hash')

    expect(manifestKeyAfter).toBe(manifestKeyBefore)
    expect(tailwindKeyAfter).toBe(tailwindKeyBefore)

    // 授权身份键也稳定：token 只作值，换票覆盖值而不改变键
    const previewAuthKey = buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_PREVIEW_TOKEN)
    const serviceAuthKey = buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN)
    expect(buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_PREVIEW_TOKEN)).toBe(previewAuthKey)
    expect(buildPreviewCacheKey(artifactId, PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN)).toBe(serviceAuthKey)

    // 缓存值可随换票更新，但命中身份不变
    const cache = new PreviewBoundedCache<string>({ maxEntries: 10, ttlMs: 60_000 })
    cache.set(previewAuthKey, previewTokenA, { artifactId })
    cache.set(previewAuthKey, previewTokenB, { artifactId })
    expect(cache.get(previewAuthKey)).toBe(previewTokenB)
    expect(cache.get(previewAuthKey)).not.toBe(previewTokenA)
    void serviceTokenA
    void serviceTokenB
  })

  it('不同 artifact 或不同内容身份产生不同键', () => {
    expect(buildPreviewCacheKey('a1', 'm')).not.toBe(buildPreviewCacheKey('a2', 'm'))
    expect(buildPreviewCacheKey('a1', 'm')).not.toBe(buildPreviewCacheKey('a1', 't'))
  })
})
