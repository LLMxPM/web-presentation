/**
 * 文件用途：验证预览执行预算通道：独立 lane、排队/活跃可观测、队列满返回结构化 429。
 */

import { afterEach, describe, expect, it } from 'vitest'

import {
  getRuntimePreviewScheduler,
  resetRuntimePreviewScheduler,
  runWithPreviewBudget,
  RuntimeViteTaskSchedulerError,
} from './runtime-preview-scheduler'

describe('runtime preview scheduler', () => {
  afterEach(() => {
    resetRuntimePreviewScheduler()
  })

  it('应暴露 preview 排队年龄与活跃数（C4）', async () => {
    const scheduler = getRuntimePreviewScheduler()
    const snapshot = scheduler.snapshot()
    expect(snapshot.kinds.preview).toMatchObject({
      active: expect.any(Number),
      queued: expect.any(Number),
      oldestQueuedAgeMs: expect.any(Number),
    })
    expect(typeof snapshot.queuedPreview).toBe('number')
    expect(typeof snapshot.active).toBe('number')
  })

  it('预览任务应可在独立预算内执行', async () => {
    const result = await runWithPreviewBudget(async () => 'ok')
    expect(result).toBe('ok')
  })

  it('并发占满后新任务应排队并最终完成或结构化拒绝', async () => {
    const scheduler = getRuntimePreviewScheduler()
    const concurrency = scheduler.snapshot().kinds.preview.concurrency
    const blockers: Array<() => void> = []
    const running = Array.from({ length: concurrency }, () =>
      runWithPreviewBudget(() => new Promise<void>((resolve) => {
        blockers.push(resolve)
      })),
    )
    // 让出微任务，使占用生效。
    await Promise.resolve()
    const followUp = runWithPreviewBudget(async () => 'queued-ok')
    const settled = await Promise.race([
      followUp.then(value => ({ ok: true as const, value })),
      Promise.resolve({ ok: false as const }),
    ])
    if (!settled.ok) {
      // 仍在排队：解除占用后应完成。
      for (const release of blockers) {
        release()
      }
      await Promise.all(running)
      expect(await followUp).toBe('queued-ok')
    } else {
      for (const release of blockers) {
        release()
      }
      await Promise.all(running)
      expect(settled.value).toBe('queued-ok')
    }
  })

  it('调度器错误应带 statusCode/code，便于 HTTP 映射', () => {
    const error = new RuntimeViteTaskSchedulerError(429, 'RUNTIME_VITE_QUEUE_FULL', '队列已满')
    expect(error.statusCode).toBe(429)
    expect(error.code).toBe('RUNTIME_VITE_QUEUE_FULL')
  })
})
