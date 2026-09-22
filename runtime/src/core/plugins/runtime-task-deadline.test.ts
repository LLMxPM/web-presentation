/**
 * 文件用途：验证 Runtime 任务 deadline 会中止网络型等待并保留超时错误码。
 */

import { describe, expect, it } from 'vitest'

import {
  RuntimeTaskDeadlineError,
  runWithRuntimeTaskDeadline,
} from './runtime-task-deadline'

describe('runtime task deadline', () => {
  it('应在 deadline 到达时 abort signal 并返回诊断超时错误', async () => {
    let aborted = false

    await expect(runWithRuntimeTaskDeadline('diagnostics', 20, async deadline => {
      await new Promise<void>((_resolveWait, rejectWait) => {
        deadline.signal.addEventListener('abort', () => {
          aborted = true
          rejectWait(deadline.signal.reason)
        }, { once: true })
      })
    })).rejects.toMatchObject({
      statusCode: 504,
      code: 'RUNTIME_DIAGNOSTICS_TASK_TIMEOUT',
    })

    expect(aborted).toBe(true)
  })

  it('应在任务完成后清除 deadline 并返回结果', async () => {
    await expect(runWithRuntimeTaskDeadline('project', 1000, async deadline => {
      expect(deadline.remainingMs()).toBeGreaterThan(0)
      return 'done'
    })).resolves.toBe('done')
  })

  it('应把任务主动抛出的业务错误原样保留', async () => {
    const sourceError = new Error('source failure')

    await expect(runWithRuntimeTaskDeadline('project', 1000, async () => {
      throw sourceError
    })).rejects.toBe(sourceError)
    expect(new RuntimeTaskDeadlineError('project', 1).code).toBe('RUNTIME_BUILD_TASK_TIMEOUT')
  })
})
