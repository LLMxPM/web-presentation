/**
 * 文件用途：验证三维模型解析缓存的引用计数、LRU 淘汰与分区语义。
 *
 * @vitest-environment jsdom
 */

import { describe, expect, it, vi, type Mock } from 'vitest'

import { ModelCache, buildModelCacheKey, type DisposableModelResource } from './model-cache'

interface FakeResource extends DisposableModelResource {
  id: string
  disposeSpy: Mock<() => void>
}

/**
 * 创建带 dispose 探针的假资源。
 * @param id 资源标识
 * @returns 假资源
 */
function createResource(id: string): FakeResource {
  const resource: FakeResource = {
    id,
    disposeSpy: vi.fn<() => void>(),
    dispose: () => {
      resource.disposeSpy()
    },
  }
  return resource
}

/**
 * 创建单调递增的时间函数，便于确定性地验证 LRU 顺序。
 * @returns 时间函数
 */
function createClock(): () => number {
  let clock = 0
  return () => {
    clock += 1
    return clock
  }
}

describe('buildModelCacheKey 分区 key', () => {
  it('应按 fileHashOrUrl|engineVersion|validationProfile 拼接', () => {
    expect(buildModelCacheKey({
      fileHashOrUrl: './product.glb',
      engineVersion: '0.186.1',
      validationProfile: 'model3d-glb-v1',
    })).toBe('./product.glb|0.186.1|model3d-glb-v1')
  })
})

describe('ModelCache 引用计数', () => {
  it('两次 acquire 只解析一次，release 一次仍存活，归零后可淘汰', async () => {
    const cache = new ModelCache<FakeResource>({ capacity: 4 })
    const resource = createResource('a')
    const factory = vi.fn(async () => resource)

    const first = await cache.acquire('k', factory)
    const second = await cache.acquire('k', factory)

    expect(factory).toHaveBeenCalledTimes(1)
    expect(first).toBe(resource)
    expect(second).toBe(resource)
    expect(cache.getRefCount('k')).toBe(2)

    cache.release('k')
    expect(cache.size()).toBe(1)
    expect(cache.getRefCount('k')).toBe(1)
    expect(resource.disposeSpy).not.toHaveBeenCalled()

    cache.release('k')
    expect(cache.getRefCount('k')).toBe(0)
    expect(cache.size()).toBe(1)
    expect(resource.disposeSpy).not.toHaveBeenCalled()
  })

  it('并发 acquire 同一 key 应复用同一个在途 Promise', async () => {
    const cache = new ModelCache<FakeResource>({ capacity: 4 })
    const resource = createResource('async')
    let resolveFactory: (value: FakeResource) => void = () => undefined
    const factory = vi.fn(() => new Promise<FakeResource>((resolve) => {
      resolveFactory = resolve
    }))

    const pending = [cache.acquire('k', factory), cache.acquire('k', factory)]
    resolveFactory(resource)
    const [first, second] = await Promise.all(pending)

    expect(factory).toHaveBeenCalledTimes(1)
    expect(first).toBe(resource)
    expect(second).toBe(resource)
    expect(cache.getRefCount('k')).toBe(2)
  })

  it('工厂失败时不应留下缓存条目或引用计数', async () => {
    const cache = new ModelCache<FakeResource>({ capacity: 4 })
    await expect(cache.acquire('k', async () => {
      throw new Error('parse failed')
    })).rejects.toThrow('parse failed')
    expect(cache.size()).toBe(0)
    expect(cache.getRefCount('k')).toBe(0)
  })
})

describe('ModelCache LRU 淘汰', () => {
  it('超出容量应淘汰最久未用且引用为 0 的条目并回调释放', async () => {
    const onEvict = vi.fn()
    const cache = new ModelCache<FakeResource>({ capacity: 2, onEvict, now: createClock() })
    const resourceA = createResource('a')
    const resourceB = createResource('b')
    const resourceC = createResource('c')

    await cache.acquire('a', async () => resourceA)
    await cache.acquire('b', async () => resourceB)
    cache.release('a')

    await cache.acquire('c', async () => resourceC)

    expect(onEvict).toHaveBeenCalledTimes(1)
    expect(onEvict).toHaveBeenCalledWith('a', resourceA)
    expect(cache.size()).toBe(2)
    expect(cache.peek('a')).toBeNull()
    expect(cache.peek('b')).not.toBeNull()
    expect(cache.peek('c')).not.toBeNull()
  })

  it('仍被引用的条目不应被淘汰，release 后才回收', async () => {
    const onEvict = vi.fn()
    const cache = new ModelCache<FakeResource>({ capacity: 2, onEvict, now: createClock() })

    await cache.acquire('a', async () => createResource('a'))
    await cache.acquire('b', async () => createResource('b'))
    await cache.acquire('c', async () => createResource('c'))

    // 三个条目都仍被引用，不允许淘汰，容量暂时被突破。
    expect(cache.size()).toBe(3)
    expect(onEvict).not.toHaveBeenCalled()

    cache.release('a')
    expect(cache.size()).toBe(2)
    expect(onEvict).toHaveBeenCalledTimes(1)
    expect(onEvict.mock.calls[0][0]).toBe('a')
  })

  it('drain 应释放全部条目', async () => {
    const onEvict = vi.fn()
    const cache = new ModelCache<FakeResource>({ capacity: 4, onEvict })
    await cache.acquire('a', async () => createResource('a'))
    await cache.acquire('b', async () => createResource('b'))

    cache.drain()

    expect(cache.size()).toBe(0)
    expect(onEvict).toHaveBeenCalledTimes(2)
  })
})

describe('ModelCache 分区共享', () => {
  it('引擎版本或校验策略不同时不共享缓存条目', async () => {
    const cache = new ModelCache<FakeResource>({ capacity: 4 })
    const factory = vi.fn(async () => createResource('shared'))

    const keyV1 = buildModelCacheKey({ fileHashOrUrl: './m.glb', engineVersion: '1', validationProfile: 'p1' })
    const keyV2 = buildModelCacheKey({ fileHashOrUrl: './m.glb', engineVersion: '2', validationProfile: 'p1' })
    const keyProfile = buildModelCacheKey({ fileHashOrUrl: './m.glb', engineVersion: '1', validationProfile: 'p2' })

    await cache.acquire(keyV1, factory)
    await cache.acquire(keyV2, factory)
    await cache.acquire(keyProfile, factory)

    expect(factory).toHaveBeenCalledTimes(3)
    expect(cache.size()).toBe(3)
  })
})
