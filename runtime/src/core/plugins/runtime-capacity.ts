/**
 * 文件用途：汇总 Runtime 进程级容量信号（事件循环延迟、内存、负载调用计数），供健康检查与阶段 0 负载定位使用。
 */

import { monitorEventLoopDelay, type IntervalHistogram } from 'perf_hooks'

import { getRuntimeRole } from './runtime-role'

export type RuntimeWorkloadKind = 'preview' | 'check' | 'build' | 'light_tool'

export interface RuntimeWorkloadCounters {
  calls: number
  totalDurationMs: number
  lastDurationMs: number
  maxDurationMs: number
}

export interface RuntimeWorkloadSnapshot {
  preview: RuntimeWorkloadCounters
  check: RuntimeWorkloadCounters
  build: RuntimeWorkloadCounters
  light_tool: RuntimeWorkloadCounters
}

export interface RuntimeEventLoopSnapshot {
  /** 最近采样窗口内的平均延迟（毫秒） */
  meanLagMs: number
  /** 最近采样窗口内的最大延迟（毫秒） */
  maxLagMs: number
  /** p99 延迟（毫秒） */
  p99LagMs: number
  /** 是否已启用采样 */
  enabled: boolean
}

export interface RuntimeMemorySnapshot {
  rssBytes: number
  heapTotalBytes: number
  heapUsedBytes: number
  externalBytes: number
  arrayBuffersBytes: number
}

export type RuntimeCapacityProvider = () => Record<string, unknown>

const EVENT_LOOP_SAMPLE_INTERVAL_MS = 20
const EMPTY_COUNTERS = (): RuntimeWorkloadCounters => ({
  calls: 0,
  totalDurationMs: 0,
  lastDurationMs: 0,
  maxDurationMs: 0,
})

const workloadCounters: RuntimeWorkloadSnapshot = {
  preview: EMPTY_COUNTERS(),
  check: EMPTY_COUNTERS(),
  build: EMPTY_COUNTERS(),
  light_tool: EMPTY_COUNTERS(),
}

const capacityProviders = new Map<string, RuntimeCapacityProvider>()

let eventLoopHistogram: IntervalHistogram | null = null
let eventLoopMonitorRef: ReturnType<typeof setInterval> | null = null

/**
 * 启动事件循环延迟采样；重复调用为幂等。
 */
export function startRuntimeEventLoopLagMonitor(): void {
  if (eventLoopHistogram) {
    return
  }
  try {
    const histogram = monitorEventLoopDelay({ resolution: EVENT_LOOP_SAMPLE_INTERVAL_MS })
    histogram.enable()
    eventLoopHistogram = histogram
    // 定时重置窗口，避免自进程启动以来的 max 失去时效。
    eventLoopMonitorRef = setInterval(() => {
      histogram.reset()
    }, 60_000)
    eventLoopMonitorRef.unref?.()
  } catch {
    // 某些受限运行时可能不可用；健康输出标记 enabled=false 即可。
    eventLoopHistogram = null
  }
}

/**
 * 停止事件循环延迟采样。
 */
export function stopRuntimeEventLoopLagMonitor(): void {
  if (eventLoopMonitorRef) {
    clearInterval(eventLoopMonitorRef)
    eventLoopMonitorRef = null
  }
  if (eventLoopHistogram) {
    eventLoopHistogram.disable()
    eventLoopHistogram = null
  }
}

/**
 * 读取当前事件循环延迟快照。
 */
export function getRuntimeEventLoopSnapshot(): RuntimeEventLoopSnapshot {
  const histogram = eventLoopHistogram
  if (!histogram) {
    return { meanLagMs: 0, maxLagMs: 0, p99LagMs: 0, enabled: false }
  }
  return {
    meanLagMs: nanosToMs(histogram.mean),
    maxLagMs: nanosToMs(histogram.max),
    p99LagMs: nanosToMs(histogram.percentile(99)),
    enabled: true,
  }
}

/**
 * 读取当前进程内存快照。
 */
export function getRuntimeMemorySnapshot(): RuntimeMemorySnapshot {
  const usage = process.memoryUsage()
  return {
    rssBytes: usage.rss,
    heapTotalBytes: usage.heapTotal,
    heapUsedBytes: usage.heapUsed,
    externalBytes: usage.external,
    arrayBuffersBytes: usage.arrayBuffers,
  }
}

/**
 * 记录一次负载调用及其耗时，用于区分预览 / Check / Build 压力来源。
 * @param kind 负载类别
 * @param durationMs 本次调用耗时（毫秒）
 */
export function recordRuntimeWorkload(kind: RuntimeWorkloadKind, durationMs: number): void {
  const counters = workloadCounters[kind]
  counters.calls += 1
  const normalized = Number.isFinite(durationMs) && durationMs >= 0 ? durationMs : 0
  counters.totalDurationMs += normalized
  counters.lastDurationMs = normalized
  counters.maxDurationMs = Math.max(counters.maxDurationMs, normalized)
}

/**
 * 读取负载调用计数快照。
 */
export function getRuntimeWorkloadSnapshot(): RuntimeWorkloadSnapshot {
  return {
    preview: { ...workloadCounters.preview },
    check: { ...workloadCounters.check },
    build: { ...workloadCounters.build },
    light_tool: { ...workloadCounters.light_tool },
  }
}

/**
 * 注册角色相关的额外容量提供者（如调度器队列、诊断工作区池）。
 * @param name 提供者名称，重复注册会覆盖
 * @param provider 返回结构化容量字段
 * @returns 取消注册函数
 */
export function registerRuntimeCapacityProvider(
  name: string,
  provider: RuntimeCapacityProvider,
): () => void {
  capacityProviders.set(name, provider)
  return () => {
    if (capacityProviders.get(name) === provider) {
      capacityProviders.delete(name)
    }
  }
}

/**
 * 汇总进程级与已注册角色容量字段。
 */
export function collectRuntimeCapacity(): Record<string, unknown> {
  const capacity: Record<string, unknown> = {
    role: getRuntimeRole(),
    memory: getRuntimeMemorySnapshot(),
    eventLoop: getRuntimeEventLoopSnapshot(),
    workloads: getRuntimeWorkloadSnapshot(),
    uptimeMs: Math.round(process.uptime() * 1000),
    pid: process.pid,
  }
  for (const [name, provider] of capacityProviders) {
    try {
      capacity[name] = provider()
    } catch (error) {
      capacity[name] = {
        error: error instanceof Error ? error.message : String(error),
      }
    }
  }
  return capacity
}

/**
 * 重置负载计数（主要用于测试）。
 */
export function resetRuntimeWorkloadCounters(): void {
  for (const kind of Object.keys(workloadCounters) as RuntimeWorkloadKind[]) {
    workloadCounters[kind] = EMPTY_COUNTERS()
  }
}

function nanosToMs(nanos: number): number {
  if (!Number.isFinite(nanos) || nanos <= 0) {
    return 0
  }
  return Math.round((nanos / 1e6) * 100) / 100
}
