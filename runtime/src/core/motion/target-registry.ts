/**
 * 文件功能：维护页内时间轴对媒体与模型目标的独占认领。
 *
 * 认领结果供 PageMediaSession 过滤：已由 transport 接管的媒体不再被旧会话
 * 自动播放、归零或重复计入完成集合；generation 变化后旧认领立即失效。
 */
import { MotionError, MOTION_ERROR_PROPERTY_CONFLICT } from './errors'
import type { MotionTrackType } from './types'

/** 需要独占的目标类型；DOM 由编译期属性所有权校验，不在此登记。 */
export type MotionClaimKind = Extract<MotionTrackType, 'audio' | 'video' | 'model3d'>

export interface MotionTargetClaim {
  readonly kind: MotionClaimKind
  readonly key: string
  readonly generation: number
  /** 幂等释放；只移除本人持有的认领。 */
  release(): void
}

interface ClaimRecord {
  kind: MotionClaimKind
  key: string
  generation: number
  element: Element | null
  token: symbol
}

/**
 * 页面级目标注册表。一次 transport 生命周期对应一个实例；
 * 不跨页面复用，也不把目标对象暴露给公共代码。
 */
export class MotionTargetRegistry {
  private readonly records = new Map<string, ClaimRecord>()
  private readonly elementTokens = new WeakMap<Element, symbol>()
  private activeGeneration = 0
  private disposed = false
  private sequence = 0

  /** 开启新的页面 generation；旧 generation 的认领全部失效。 */
  beginGeneration(generation: number): void {
    this.activeGeneration = generation
    this.records.clear()
  }

  /**
   * 认领一个目标。媒体/模型同名目标在同一 generation 内只能被一个轨道占用。
   * @throws MotionError 目标已被其它轨道认领
   */
  claim(kind: MotionClaimKind, key: string, element: Element | null, generation = this.activeGeneration): MotionTargetClaim {
    if (this.disposed) {
      throw new MotionError(MOTION_ERROR_PROPERTY_CONFLICT, '目标注册表已释放。')
    }
    const normalizedKey = `${kind}:${key}`
    const existing = this.records.get(normalizedKey)
    if (existing && existing.generation === generation) {
      throw new MotionError(MOTION_ERROR_PROPERTY_CONFLICT, `目标 ${key} 已被其它轨道认领。`)
    }
    const token = Symbol(`motion-target-${++this.sequence}`)
    const record: ClaimRecord = { kind, key: normalizedKey, generation, element, token }
    this.records.set(normalizedKey, record)
    if (element) this.elementTokens.set(element, token)
    let released = false
    return {
      kind,
      key: normalizedKey,
      generation,
      release: () => {
        if (released) return
        released = true
        const current = this.records.get(normalizedKey)
        if (current?.token === token) this.records.delete(normalizedKey)
        if (element && this.elementTokens.get(element) === token) {
          this.elementTokens.delete(element)
        }
      },
    }
  }

  /**
   * 判断媒体元素是否已由当前 generation 的时间轴认领。
   * 旧 generation 的残留 token 不阻止新页面会话接管。
   */
  isElementClaimed(element: Element, generation = this.activeGeneration): boolean {
    if (this.disposed) return false
    const token = this.elementTokens.get(element)
    if (!token) return false
    for (const record of this.records.values()) {
      if (record.token === token) return record.generation === generation
    }
    return false
  }

  /** 当前 generation 是否认领了指定逻辑目标。 */
  hasClaim(kind: MotionClaimKind, key: string, generation = this.activeGeneration): boolean {
    const record = this.records.get(`${kind}:${key}`)
    return Boolean(record && record.generation === generation)
  }

  /** 释放全部认领；dispose 后不再接受新目标。 */
  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.records.clear()
  }
}
