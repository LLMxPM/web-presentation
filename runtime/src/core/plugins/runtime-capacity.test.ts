/**
 * 文件用途：验证 Runtime 容量信号采集：负载计数、事件循环快照与容量提供者汇总。
 */

import { afterEach, describe, expect, it } from 'vitest'

import {
  collectRuntimeCapacity,
  getRuntimeEventLoopSnapshot,
  getRuntimeMemorySnapshot,
  getRuntimeWorkloadSnapshot,
  recordRuntimeWorkload,
  registerRuntimeCapacityProvider,
  resetRuntimeWorkloadCounters,
  startRuntimeEventLoopLagMonitor,
  stopRuntimeEventLoopLagMonitor,
} from './runtime-capacity'

describe('runtime capacity', () => {
  afterEach(() => {
    resetRuntimeWorkloadCounters()
    stopRuntimeEventLoopLagMonitor()
  })

  it('应累计各负载类别的调用次数与耗时', () => {
    recordRuntimeWorkload('build', 100)
    recordRuntimeWorkload('build', 50)
    recordRuntimeWorkload('check', 20)

    const snapshot = getRuntimeWorkloadSnapshot()
    expect(snapshot.build).toEqual({
      calls: 2,
      totalDurationMs: 150,
      lastDurationMs: 50,
      maxDurationMs: 100,
      errors: 0,
      timeouts: 0,
    })
    expect(snapshot.check.calls).toBe(1)
    expect(snapshot.preview.calls).toBe(0)
  })

  it('应累计失败与超时调用，便于容量输出对账错误率', () => {
    recordRuntimeWorkload('preview', 10, 'error')
    recordRuntimeWorkload('preview', 20, 'timeout')
    recordRuntimeWorkload('preview', 5)

    const snapshot = getRuntimeWorkloadSnapshot()
    expect(snapshot.preview.errors).toBe(1)
    expect(snapshot.preview.timeouts).toBe(1)
    expect(snapshot.preview.calls).toBe(3)
  })

  it('应输出进程内存字段', () => {
    const memory = getRuntimeMemorySnapshot()
    expect(memory.rssBytes).toBeGreaterThan(0)
    expect(memory.heapUsedBytes).toBeGreaterThan(0)
    expect(memory.heapTotalBytes).toBeGreaterThan(0)
  })

  it('启动后应能读取事件循环延迟快照', () => {
    startRuntimeEventLoopLagMonitor()
    startRuntimeEventLoopLagMonitor()
    const snapshot = getRuntimeEventLoopSnapshot()
    expect(snapshot.enabled).toBe(true)
    expect(snapshot.meanLagMs).toBeGreaterThanOrEqual(0)
    expect(snapshot.maxLagMs).toBeGreaterThanOrEqual(0)
  })

  it('应汇总注册的容量提供者，提供者异常不影响其它字段', () => {
    const unregister = registerRuntimeCapacityProvider('okProvider', () => ({ value: 1 }))
    registerRuntimeCapacityProvider('badProvider', () => {
      throw new Error('provider failed')
    })

    const capacity = collectRuntimeCapacity()
    expect(capacity.okProvider).toEqual({ value: 1 })
    expect(capacity.badProvider).toMatchObject({ error: 'provider failed' })
    expect(capacity.memory).toBeTruthy()

    unregister()
    expect(collectRuntimeCapacity().okProvider).toBeUndefined()
  })
})
