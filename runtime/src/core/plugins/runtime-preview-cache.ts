/**
 * 文件功能：预览侧进程内有界缓存（LRU + TTL）与稳定内容身份键构造。
 *
 * 设计原则（T3-2）：
 * - 缓存只用于提速，副本丢失缓存不影响正确性；
 * - 计算缓存键使用稳定内容身份（artifact_id + 内容 hash/版本），短期授权 token 只作值、不作主键；
 * - 换票（服务令牌轮换）或 preview token 更新不改变同一内容的计算缓存身份；
 * - artifact 失效时按 artifact 清理全部相关条目，旧缓存不得继续声称可用。
 */

/** 默认容量：单类缓存条目上限，超出按 LRU 淘汰。 */
export const DEFAULT_PREVIEW_CACHE_MAX_ENTRIES = 200

/** 默认过期时间：条目仅用于加速，过期后重新回源。 */
export const DEFAULT_PREVIEW_CACHE_TTL_MS = 10 * 60_000

/** 内容身份：artifact manifest（artifact 不可变，manifest 即内容身份）。 */
export const PREVIEW_CACHE_IDENTITY_MANIFEST = 'manifest'

/** 内容身份：预览上下文令牌（授权身份，值随换票轮换，键保持稳定）。 */
export const PREVIEW_CACHE_IDENTITY_PREVIEW_TOKEN = 'auth:preview-token'

/** 内容身份：Runtime 服务令牌（授权身份，值随换票轮换，键保持稳定）。 */
export const PREVIEW_CACHE_IDENTITY_SERVICE_TOKEN = 'auth:service-token'

interface PreviewCacheRecord<V> {
  value: V
  artifactId: string
  expiresAtMs: number
}

export interface PreviewBoundedCacheOptions {
  /** 条目数量上限，超出按 LRU 淘汰 */
  maxEntries?: number
  /** 默认 TTL（毫秒） */
  ttlMs?: number
  /** 时钟来源，便于测试注入 */
  now?: () => number
}

/**
 * 有界进程内缓存：LRU 容量淘汰 + TTL 过期 + 按 artifact 失效。
 * 仅用于加速，不构成正确性依赖。
 */
export class PreviewBoundedCache<V> {
  private readonly store = new Map<string, PreviewCacheRecord<V>>()
  private readonly maxEntries: number
  private readonly defaultTtlMs: number
  private readonly now: () => number

  constructor(options: PreviewBoundedCacheOptions = {}) {
    this.maxEntries = normalizePositiveInteger(options.maxEntries, DEFAULT_PREVIEW_CACHE_MAX_ENTRIES)
    this.defaultTtlMs = normalizePositiveInteger(options.ttlMs, DEFAULT_PREVIEW_CACHE_TTL_MS)
    // 包装为闭包，便于测试替换 Date.now 后仍生效
    this.now = options.now || (() => Date.now())
  }

  /**
   * 读取未过期条目并刷新 LRU 位置；过期条目顺带删除。
   * @param key 缓存键
   * @returns 条目值；缺失或过期返回 undefined
   */
  get(key: string): V | undefined {
    const record = this.store.get(key)
    if (!record) {
      return undefined
    }
    if (record.expiresAtMs <= this.now()) {
      this.store.delete(key)
      return undefined
    }
    // 命中后移到队尾，保持 Map 插入顺序即 LRU 顺序
    this.store.delete(key)
    this.store.set(key, record)
    return record.value
  }

  /**
   * 写入条目并执行容量淘汰。
   * @param key 缓存键
   * @param value 缓存值
   * @param meta 归属 artifact（用于失效）与可选 TTL
   */
  set(key: string, value: V, meta: { artifactId: string; ttlMs?: number }): void {
    const ttlMs = normalizePositiveInteger(meta.ttlMs, this.defaultTtlMs)
    this.store.delete(key)
    this.store.set(key, {
      value,
      artifactId: String(meta.artifactId || ''),
      expiresAtMs: this.now() + ttlMs,
    })
    this.evictOverflow()
  }

  /**
   * 删除指定键。
   * @param key 缓存键
   * @returns 是否删除了条目
   */
  delete(key: string): boolean {
    return this.store.delete(key)
  }

  /**
   * 清空全部条目。
   */
  clear(): void {
    this.store.clear()
  }

  /**
   * 当前有效条目数（惰性清理过期条目）。
   */
  get size(): number {
    this.pruneExpired()
    return this.store.size
  }

  /**
   * 清除指定 artifact 的全部缓存条目；artifact 失效时必须调用，避免旧缓存继续声称可用。
   * @param artifactId preview artifact ID
   * @returns 清除的条目数
   */
  invalidateArtifact(artifactId: string): number {
    const target = String(artifactId || '')
    if (!target) {
      return 0
    }
    let removed = 0
    for (const [key, record] of this.store) {
      if (record.artifactId === target) {
        this.store.delete(key)
        removed += 1
      }
    }
    return removed
  }

  /**
   * 删除满足谓词的条目（供定制失效与测试使用）。
   * @param predicate 键值谓词
   * @returns 删除数量
   */
  deleteIf(predicate: (key: string, value: V) => boolean): number {
    let removed = 0
    for (const [key, record] of this.store) {
      if (predicate(key, record.value)) {
        this.store.delete(key)
        removed += 1
      }
    }
    return removed
  }

  /** 淘汰超出容量的最久未使用条目。 */
  private evictOverflow(): void {
    while (this.store.size > this.maxEntries) {
      const oldestKey = this.store.keys().next().value
      if (oldestKey === undefined) {
        return
      }
      this.store.delete(oldestKey)
    }
  }

  /** 清理全部过期条目。 */
  private pruneExpired(): void {
    const nowMs = this.now()
    for (const [key, record] of this.store) {
      if (record.expiresAtMs <= nowMs) {
        this.store.delete(key)
      }
    }
  }
}

/**
 * 构造预览缓存键：artifact_id + 稳定内容身份。
 * 短期授权 token 不参与键构造，换票不会产生新的缓存身份。
 * @param artifactId preview artifact ID
 * @param contentIdentity 内容 hash 或版本标识（如 manifest、源码签名、模块路径）
 * @returns 稳定缓存键
 */
export function buildPreviewCacheKey(artifactId: string, contentIdentity: string): string {
  return `${String(artifactId || '')}\u0000${String(contentIdentity || '')}`
}

/**
 * 规范化正整数配置。
 * @param value 原始值
 * @param fallback 兜底值
 * @returns 规范化后的正整数
 */
function normalizePositiveInteger(value: unknown, fallback: number): number {
  const normalized = Number(value)
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return fallback
  }
  return Math.round(normalized)
}
