/**
 * 文件用途：验证 Runtime Vite 调度器的并发上限、加权公平、队列边界与关闭语义。
 */

import { describe, expect, it, vi } from 'vitest'

import {
  RuntimeViteTaskScheduler,
  RuntimeViteTaskSchedulerError,
} from './runtime-vite-task-scheduler'

describe('runtime vite task scheduler', () => {
  it('应在诊断与正式构建之间共享并发上限', async () => {
    const scheduler = new RuntimeViteTaskScheduler({ concurrency: 2, maxQueueSize: 8 })
    let active = 0
    let maxActive = 0
    const gates = Array.from({ length: 4 }, createDeferred)
    const tasks = gates.map((gate, index) => scheduler.schedule(
      index % 2 === 0 ? 'diagnostics' : 'project',
      async () => {
        active += 1
        maxActive = Math.max(maxActive, active)
        await gate.promise
        active -= 1
      },
    ))

    await vi.waitFor(() => expect(active).toBe(2))
    gates.forEach(gate => gate.resolve())
    await Promise.all(tasks)

    expect(maxActive).toBe(2)
    scheduler.close()
  })

  it('双方均等待时应按三个诊断后执行一个正式构建', async () => {
    const scheduler = new RuntimeViteTaskScheduler({ concurrency: 1, diagnosticsWeight: 3 })
    const firstGate = createDeferred()
    const order: string[] = []
    const first = scheduler.schedule('diagnostics', async () => {
      order.push('running')
      await firstGate.promise
    })
    const queued = [
      scheduler.schedule('diagnostics', async () => { order.push('d1') }),
      scheduler.schedule('diagnostics', async () => { order.push('d2') }),
      scheduler.schedule('diagnostics', async () => { order.push('d3') }),
      scheduler.schedule('diagnostics', async () => { order.push('d4') }),
      scheduler.schedule('project', async () => { order.push('p1') }),
    ]

    firstGate.resolve()
    await Promise.all([first, ...queued])

    expect(order).toEqual(['running', 'd1', 'd2', 'p1', 'd3', 'd4'])
    scheduler.close()
  })

  it('队列满时应立即返回结构化 429 错误', async () => {
    const scheduler = new RuntimeViteTaskScheduler({ concurrency: 1, maxQueueSize: 1 })
    const gate = createDeferred()
    const running = scheduler.schedule('diagnostics', async () => gate.promise)
    const queued = scheduler.schedule('diagnostics', async () => undefined)

    await expect(scheduler.schedule('project', async () => undefined)).rejects.toMatchObject({
      statusCode: 429,
      code: 'RUNTIME_VITE_QUEUE_FULL',
    })
    gate.resolve()
    await Promise.all([running, queued])
    scheduler.close()
  })

  it('等待超时与关闭均应拒绝尚未开始的任务', async () => {
    const scheduler = new RuntimeViteTaskScheduler({ concurrency: 1, queueWaitTimeoutMs: 10 })
    const gate = createDeferred()
    const running = scheduler.schedule('diagnostics', async () => gate.promise)
    const timedOut = scheduler.schedule('project', async () => undefined)

    await expect(timedOut).rejects.toMatchObject({
      statusCode: 429,
      code: 'RUNTIME_VITE_QUEUE_TIMEOUT',
    })
    scheduler.close()
    await expect(scheduler.schedule('diagnostics', async () => undefined)).rejects.toBeInstanceOf(
      RuntimeViteTaskSchedulerError,
    )
    gate.resolve()
    await running
  })
})

interface Deferred {
  promise: Promise<void>
  resolve: () => void
}

/**
 * 创建由测试控制完成时机的 Promise。
 */
function createDeferred(): Deferred {
  let resolve = () => undefined
  const promise = new Promise<void>(done => {
    resolve = done
  })
  return { promise, resolve }
}
