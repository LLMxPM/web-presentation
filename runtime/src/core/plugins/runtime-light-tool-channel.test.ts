/**
 * 文件用途：验证轻量内部工具独立通道的并发上限、超时与超限错误结构。
 */

import { afterEach, describe, expect, it } from 'vitest'

import {
  resetRuntimeLightToolChannel,
  runWithLightToolBudget,
} from './runtime-light-tool-channel'

describe('runtime light tool channel', () => {
  const originalEnv = { ...process.env }

  afterEach(() => {
    resetRuntimeLightToolChannel()
    for (const key of Object.keys(process.env)) {
      if (!(key in originalEnv)) {
        delete process.env[key]
      }
    }
    Object.assign(process.env, originalEnv)
  })

  it('轻量任务应独立限并发执行，不受长编译队列影响', async () => {
    process.env.RUNTIME_LIGHT_TOOL_CONCURRENCY = '2'
    process.env.RUNTIME_LIGHT_TOOL_QUEUE_SIZE = '8'
    resetRuntimeLightToolChannel()
    let active = 0
    let maxActive = 0
    const tasks = Array.from({ length: 4 }, () => runWithLightToolBudget(async () => {
      active += 1
      maxActive = Math.max(maxActive, active)
      await new Promise(resolve => setTimeout(resolve, 5))
      active -= 1
    }))

    await Promise.all(tasks)
    expect(maxActive).toBeLessThanOrEqual(2)
  })

  it('超过执行时限应返回结构化 504', async () => {
    await expect(runWithLightToolBudget(
      () => new Promise(resolve => { setTimeout(() => resolve('late'), 50) }),
      5,
    )).rejects.toMatchObject({
      statusCode: 504,
      code: 'RUNTIME_LIGHT_TOOL_TIMEOUT',
    })
  })

  it('队列打满应返回结构化 429', async () => {
    process.env.RUNTIME_LIGHT_TOOL_CONCURRENCY = '1'
    process.env.RUNTIME_LIGHT_TOOL_QUEUE_SIZE = '1'
    resetRuntimeLightToolChannel()
    const gate = createDeferred()
    const running = runWithLightToolBudget(() => gate.promise)
    const queued = runWithLightToolBudget(async () => undefined)
    await expect(runWithLightToolBudget(async () => undefined)).rejects.toMatchObject({
      statusCode: 429,
      code: 'RUNTIME_VITE_QUEUE_FULL',
    })

    gate.resolve()
    await running
    await queued
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
