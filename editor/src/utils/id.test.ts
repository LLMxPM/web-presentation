/**
 * 文件功能：验证浏览器端 UUID 工具在原生能力缺失时仍可稳定生成 v4 UUID。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { createClientUuid } from '@/utils/id'

describe('createClientUuid', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('优先使用原生 crypto.randomUUID', () => {
    const nativeUuid = '11111111-2222-4333-8444-555555555555'
    const randomUUID = vi.fn(() => nativeUuid)
    vi.stubGlobal('crypto', { randomUUID })

    expect(createClientUuid()).toBe(nativeUuid)
    expect(randomUUID).toHaveBeenCalledOnce()
  })

  it('在缺少 randomUUID 时使用 getRandomValues 生成 v4 UUID', () => {
    const getRandomValues = vi.fn((target: Uint8Array) => {
      target.forEach((_, index) => {
        target[index] = index
      })
      return target
    })
    vi.stubGlobal('crypto', { getRandomValues })

    expect(createClientUuid()).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f')
    expect(getRandomValues).toHaveBeenCalledOnce()
  })

  it('在原生 randomUUID 调用失败时降级生成 v4 UUID', () => {
    const randomUUID = vi.fn(() => {
      throw new Error('randomUUID unavailable')
    })
    const getRandomValues = vi.fn((target: Uint8Array) => {
      target.fill(255)
      return target
    })
    vi.stubGlobal('crypto', { randomUUID, getRandomValues })

    expect(createClientUuid()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff')
    expect(randomUUID).toHaveBeenCalledOnce()
    expect(getRandomValues).toHaveBeenCalledOnce()
  })

  it('在缺少 crypto 时仍返回 v4 UUID 格式', () => {
    vi.stubGlobal('crypto', undefined)
    vi.spyOn(Math, 'random').mockReturnValue(0)

    expect(createClientUuid()).toBe('00000000-0000-4000-8000-000000000000')
  })
})
