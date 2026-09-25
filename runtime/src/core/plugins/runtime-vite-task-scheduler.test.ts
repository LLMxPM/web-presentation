/**
 * 文件用途：验证 Runtime Vite 调度器按类别隔离容量、队列边界与关闭语义。
 */

import { describe, expect, it, vi } from 'vitest'

import {
  RuntimeViteTaskScheduler,
  RuntimeViteTaskSchedulerError,
} from './runtime-vite-task-scheduler'

describe('runtime vite task scheduler', () => {
  it('诊断与正式构建应各自持有独立并发容量，长构建不占用诊断槽位', async () => {
    const scheduler = new RuntimeViteTaskScheduler({
      kinds: {
        diagnostics: { concurrency: 1 },
        project: { concurrency: 1 },
      },
    })
    let projectActive = 0
    let diagnosticsActive = 0
    let maxDiagnosticsWhileProject = 0
    const projectGate = createDeferred()
    const project = scheduler.schedule('project', async () => {
      projectActive += 1
      await projectGate.promise
      projectActive -= 1
    })
    const diagnosticsGate = createDeferred()
    const diagnostics = scheduler.schedule('diagnostics', async () => {
      diagnosticsActive += 1
      maxDiagnosticsWhileProject = Math.max(maxDiagnosticsWhileProject, projectActive)
      await diagnosticsGate.promise
      diagnosticsActive -= 1
    })

    await vi.waitFor(() => {
      expect(projectActive).toBe(1)
      expect(diagnosticsActive).toBe(1)
    })
    // 长构建仍在执行时诊断已并行运行，证明容量按类别隔离而非共享 activeCount。
    expect(maxDiagnosticsWhileProject).toBe(1)

    projectGate.resolve()
    diagnosticsGate.resolve()
    await Promise.all([project, diagnostics])
    scheduler.close()
  })

  it('轻量工具不应排在长编译之后', async () => {
    const scheduler = new RuntimeViteTaskScheduler({
      kinds: {
        project: { concurrency: 1 },
        light: { concurrency: 2 },
      },
    })
    const projectGate = createDeferred()
    const project = scheduler.schedule('project', async () => projectGate.promise)

    const lightOrder: string[] = []
    const lightTasks = [
      scheduler.schedule('light', async () => { lightOrder.push('l1') }),
      scheduler.schedule('light', async () => { lightOrder.push('l2') }),
    ]

    await Promise.all(lightTasks)
    expect(lightOrder).toEqual(['l1', 'l2'])

    projectGate.resolve()
    await project
    scheduler.close()
  })

  it('单类别队列满时应立即返回结构化 429，且不影响其它类别', async () => {
    const scheduler = new RuntimeViteTaskScheduler({
      kinds: {
        diagnostics: { concurrency: 1, maxQueueSize: 1 },
        project: { concurrency: 1, maxQueueSize: 8 },
      },
    })
    const gate = createDeferred()
    const running = scheduler.schedule('diagnostics', async () => gate.promise)
    const queued = scheduler.schedule('diagnostics', async () => undefined)

    await expect(scheduler.schedule('diagnostics', async () => undefined)).rejects.toMatchObject({
      statusCode: 429,
      code: 'RUNTIME_VITE_QUEUE_FULL',
    })
    // 其它类别的准入不受该类别队列打满影响。
    const projectTask = scheduler.schedule('project', async () => 'ok')
    await expect(projectTask).resolves.toBe('ok')

    gate.resolve()
    await Promise.all([running, queued])
    scheduler.close()
  })

  it('等待超时与关闭均应拒绝尚未开始的任务', async () => {
    const scheduler = new RuntimeViteTaskScheduler({
      kinds: {
        diagnostics: { concurrency: 1, queueWaitTimeoutMs: 10 },
        project: { concurrency: 1 },
      },
    })
    const gate = createDeferred()
    const running = scheduler.schedule('diagnostics', async () => gate.promise)
    const timedOut = scheduler.schedule('diagnostics', async () => undefined)

    await expect(timedOut).rejects.toMatchObject({
      statusCode: 429,
      code: 'RUNTIME_VITE_QUEUE_TIMEOUT',
    })
    scheduler.close()
    await expect(scheduler.schedule('project', async () => undefined)).rejects.toBeInstanceOf(
      RuntimeViteTaskSchedulerError,
    )
    gate.resolve()
    await running
  })

  it('snapshot 应暴露各类别排队年龄与容量上限', async () => {
    const scheduler = new RuntimeViteTaskScheduler({
      kinds: {
        diagnostics: { concurrency: 1, maxQueueSize: 4 },
        project: { concurrency: 2 },
      },
    })
    const gate = createDeferred()
    const running = scheduler.schedule('project', async () => gate.promise)
    // 诊断类别并发 1：首条立即执行，第二条进入该类别队列，证明容量按类别独立统计。
    const runningDiagnostics = scheduler.schedule('diagnostics', async () => gate.promise)
    scheduler.schedule('diagnostics', async () => undefined)

    const snapshot = scheduler.snapshot()
    expect(snapshot.active).toBe(2)
    expect(snapshot.queuedDiagnostics).toBe(1)
    expect(snapshot.queuedProject).toBe(0)
    expect(snapshot.kinds.diagnostics.concurrency).toBe(1)
    expect(snapshot.kinds.diagnostics.maxQueueSize).toBe(4)
    expect(snapshot.kinds.project.concurrency).toBe(2)
    expect(snapshot.oldestQueuedAgeMs).toBeGreaterThanOrEqual(0)
    expect(snapshot.closed).toBe(false)

    gate.resolve()
    await Promise.all([running, runningDiagnostics])
    await Promise.resolve()
    scheduler.close()
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
