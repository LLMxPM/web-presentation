/**
 * 文件用途：三维模型解析结果的共享缓存。
 *
 * 解析结果（几何/材质/纹理的 CPU 数据）在同一页面内被多个实例共享，避免重复下载与解析；
 * 实例通过 clone 得到独立的节点与骨骼，卸载一个实例只递减引用计数，不会释放其他实例仍在使用的资源。
 *
 * 分区 key 为 `${fileHashOrUrl}|${engineVersion}|${validationProfile}`：引擎版本或校验策略变化时不共享。
 * 缓存容量有上限，超出时淘汰“最久未使用且引用计数为 0”的条目，并通过回调释放其 GPU 资源。
 */

/** 可释放资源的最小约定，由引擎侧解析结果实现。 */
export interface DisposableModelResource {
  dispose(): void
}

export interface ModelCacheOptions<T extends DisposableModelResource> {
  /** 容量上限，缺省 4。 */
  capacity?: number
  /** 条目被淘汰时的释放回调。 */
  onEvict?: (key: string, value: T) => void
  /** 取时间戳的函数，便于单测注入。 */
  now?: () => number
}

/** 缓存对外暴露的只读条目视图，供单测与诊断使用。 */
export interface ModelCacheEntryView<T> {
  key: string
  value: T | undefined
  refCount: number
  lastUsedAt: number
  pending: boolean
}

interface InternalEntry<T> extends DisposableModelResource {
  key: string
  value?: T
  pending?: Promise<T>
  refCount: number
  lastUsedAt: number
}

const DEFAULT_CACHE_CAPACITY = 4

/**
 * 构建缓存分区 key，保证不同引擎版本/校验策略不共享条目。
 * @param params 分区参数
 * @returns 缓存 key
 */
export function buildModelCacheKey(params: {
  fileHashOrUrl: string
  engineVersion: string
  validationProfile: string
}): string {
  return `${params.fileHashOrUrl}|${params.engineVersion}|${params.validationProfile}`
}

/**
 * 解析结果共享缓存：引用计数 + LRU 淘汰。
 */
export class ModelCache<T extends DisposableModelResource> {
  private readonly entries = new Map<string, InternalEntry<T>>()
  private readonly capacity: number
  private readonly onEvict?: (key: string, value: T) => void
  private readonly now: () => number

  constructor(options: ModelCacheOptions<T> = {}) {
    const capacity = Number(options.capacity)
    this.capacity = Number.isFinite(capacity) && capacity > 0 ? Math.floor(capacity) : DEFAULT_CACHE_CAPACITY
    this.onEvict = options.onEvict
    this.now = options.now ?? (() => Date.now())
  }

  /**
   * 获取或创建缓存条目并递增引用计数；并发 acquire 同一 key 只会执行一次工厂。
   * @param key 缓存 key
   * @param factory 首次创建时的异步工厂
   * @returns 解析结果
   */
  async acquire(key: string, factory: () => Promise<T>): Promise<T> {
    const existing = this.entries.get(key)
    if (existing) {
      existing.refCount += 1
      existing.lastUsedAt = this.now()
      if (existing.value !== undefined) {
        return existing.value
      }
      if (existing.pending) {
        return existing.pending
      }
    }

    const entry: InternalEntry<T> = {
      key,
      refCount: 1,
      lastUsedAt: this.now(),
      dispose: () => {
        if (entry.value !== undefined) {
          entry.value.dispose()
        }
      },
    }
    this.entries.set(key, entry)

    entry.pending = factory().then(
      (value) => {
        entry.value = value
        entry.pending = undefined
        this.evictIfNeeded()
        return value
      },
      (error) => {
        // 创建失败：移除占位，避免缓存半成品与错误的引用计数。
        if (this.entries.get(key) === entry) {
          this.entries.delete(key)
        }
        throw error
      },
    )

    return entry.pending
  }

  /**
   * 递减引用计数；仅当计数归零后条目才可被后续淘汰。
   * @param key 缓存 key
   */
  release(key: string): void {
    const entry = this.entries.get(key)
    if (!entry) {
      return
    }
    entry.refCount = Math.max(0, entry.refCount - 1)
    this.evictIfNeeded()
  }

  /**
   * 清空全部缓存并释放所有已完成的条目。
   */
  drain(): void {
    for (const key of Array.from(this.entries.keys())) {
      this.evict(key, { requireUnused: false })
    }
    this.entries.clear()
  }

  /**
   * 读取当前条目数，供单测与诊断使用。
   * @returns 条目数
   */
  size(): number {
    return this.entries.size
  }

  /**
   * 读取指定 key 的引用计数，供单测与诊断使用。
   * @param key 缓存 key
   * @returns 引用计数；不存在时返回 0
   */
  getRefCount(key: string): number {
    return this.entries.get(key)?.refCount ?? 0
  }

  /**
   * 读取指定 key 的只读条目视图，供单测与诊断使用。
   * @param key 缓存 key
   * @returns 条目视图；不存在时返回 null
   */
  peek(key: string): ModelCacheEntryView<T> | null {
    const entry = this.entries.get(key)
    if (!entry) {
      return null
    }
    return {
      key: entry.key,
      value: entry.value,
      refCount: entry.refCount,
      lastUsedAt: entry.lastUsedAt,
      pending: Boolean(entry.pending),
    }
  }

  /**
   * 按容量上限淘汰最久未使用且引用计数为 0 的条目。
   */
  private evictIfNeeded(): void {
    while (this.entries.size > this.capacity) {
      const victim = this.findEvictionCandidate()
      if (!victim) {
        // 所有超限条目都仍被引用：保留在内存中，等待后续 release 再次触发淘汰。
        return
      }
      this.evict(victim)
    }
  }

  /**
   * 查找淘汰候选：引用计数为 0 且 lastUsedAt 最小；不淘汰仍在创建中的条目。
   * @returns 候选 key；无候选时返回 null
   */
  private findEvictionCandidate(): string | null {
    let candidateKey: string | null = null
    let candidateTime = Number.POSITIVE_INFINITY
    for (const entry of this.entries.values()) {
      if (entry.refCount > 0 || entry.pending) {
        continue
      }
      if (entry.lastUsedAt < candidateTime) {
        candidateTime = entry.lastUsedAt
        candidateKey = entry.key
      }
    }
    return candidateKey
  }

  /**
   * 移除并释放指定条目。
   * @param key 缓存 key
   * @param options.requireUnused 为 true 时仅淘汰未被引用的条目（默认）
   */
  private evict(key: string, options: { requireUnused?: boolean } = {}): void {
    const entry = this.entries.get(key)
    if (!entry) {
      return
    }
    const requireUnused = options.requireUnused !== false
    if (requireUnused && entry.refCount > 0) {
      return
    }
    this.entries.delete(key)
    if (entry.value !== undefined) {
      if (this.onEvict) {
        this.onEvict(key, entry.value)
      } else {
        entry.value.dispose()
      }
    }
  }
}
