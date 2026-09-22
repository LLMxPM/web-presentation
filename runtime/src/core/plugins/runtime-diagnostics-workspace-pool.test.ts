/**
 * 文件用途：验证诊断预热工作区的复用、任务隔离、源码代次失效与模块路径守卫。
 */

import { mkdtemp, mkdir, readFile, rm, writeFile } from 'fs/promises'
import os from 'os'
import { join, resolve } from 'path'

import { describe, expect, it, vi } from 'vitest'

import {
  RuntimeDiagnosticsWorkspacePool,
  resolveWritableRuntimeModulePath,
} from './runtime-diagnostics-workspace-pool'

describe('runtime diagnostics workspace pool', () => {
  it('应复用基础工作区并在任务间恢复动态源码', async () => {
    const runtimeRoot = await createRuntimeFixture()
    const pool = new RuntimeDiagnosticsWorkspacePool({ runtimeRoot, size: 1, reuseWorker: false })
    try {
      const first = await pool.acquire()
      const firstRoot = first.tempRoot
      const target = resolveWritableRuntimeModulePath(first.tempRoot, 'src/views/RemotePage.vue')
      await writeFile(target.targetPath, '<template>remote</template>', 'utf-8')
      await first.release()

      const second = await pool.acquire()
      expect(second.tempRoot).toBe(firstRoot)
      expect(second.taskId).not.toBe(first.taskId)
      await expect(readFile(resolve(second.tempRoot, 'src/views/RemotePage.vue'), 'utf-8')).rejects.toThrow()
      expect(await readFile(resolve(second.tempRoot, 'src/views/Builtin.vue'), 'utf-8')).toContain('builtin')
      await second.release()
    } finally {
      await pool.close()
      await rm(runtimeRoot, { recursive: true, force: true })
    }
  })

  it('Runtime 基准源码变化后应销毁并重建旧槽位', async () => {
    const runtimeRoot = await createRuntimeFixture()
    const pool = new RuntimeDiagnosticsWorkspacePool({ runtimeRoot, size: 1, reuseWorker: false })
    try {
      const first = await pool.acquire()
      const firstRoot = first.tempRoot
      await first.release()
      await writeFile(resolve(runtimeRoot, 'src/views/Builtin.vue'), '<template>changed-source-longer</template>', 'utf-8')

      const second = await pool.acquire()
      expect(second.tempRoot).not.toBe(firstRoot)
      expect(await readFile(resolve(second.tempRoot, 'src/views/Builtin.vue'), 'utf-8')).toContain('changed-source')
      await second.release()
    } finally {
      await pool.close()
      await rm(runtimeRoot, { recursive: true, force: true })
    }
  })

  it('只应允许 views 与 workspace-components 内的相对模块路径', () => {
    const root = resolve(os.tmpdir(), 'runtime-path-guard')

    expect(resolveWritableRuntimeModulePath(root, '@/views/Page.vue').logicalPath).toBe('src/views/Page.vue')
    expect(resolveWritableRuntimeModulePath(root, 'src/workspace-components/Card.vue').logicalPath)
      .toBe('src/workspace-components/Card.vue')
    expect(() => resolveWritableRuntimeModulePath(root, '../outside.ts')).toThrowError(/允许目录/)
    expect(() => resolveWritableRuntimeModulePath(root, 'src/views/../../core/secret.ts')).toThrowError(/允许目录/)
    expect(() => resolveWritableRuntimeModulePath(root, 'src/runtime-kit/public/secret.ts')).toThrowError(/允许目录/)
    expect(() => resolveWritableRuntimeModulePath(root, resolve(root, 'src/views/Page.vue'))).toThrowError(/允许目录/)
  })

  it('close 在源码代次刷新期间发生时，acquire 不得重新创建或返回工作区', async () => {
    const runtimeRoot = await createRuntimeFixture()
    const pool = new RuntimeDiagnosticsWorkspacePool({ runtimeRoot, size: 1, reuseWorker: false })
    const refreshGate = createDeferred()
    const internals = pool as unknown as { refreshSourceGeneration: () => Promise<void> }
    const refreshSpy = vi.spyOn(internals, 'refreshSourceGeneration').mockImplementation(() => refreshGate.promise)
    try {
      const acquisition = pool.acquire()
      await vi.waitFor(() => expect(refreshSpy).toHaveBeenCalledTimes(1))

      await pool.close()
      refreshGate.resolve()

      await expect(acquisition).rejects.toMatchObject({
        statusCode: 503,
        code: 'RUNTIME_DIAGNOSTICS_POOL_CLOSED',
      })
      expect(pool.snapshot()).toMatchObject({ ready: 0, busy: 0 })
    } finally {
      refreshGate.resolve()
      refreshSpy.mockRestore()
      await pool.close()
      await rm(runtimeRoot, { recursive: true, force: true })
    }
  })
})

/**
 * 创建只包含工作区池所需文件的最小 Runtime fixture。
 */
async function createRuntimeFixture(): Promise<string> {
  const root = await mkdtemp(join(os.tmpdir(), 'runtime-diagnostics-pool-test-'))
  await mkdir(resolve(root, 'src/views'), { recursive: true })
  await mkdir(resolve(root, 'src/workspace-components'), { recursive: true })
  await mkdir(resolve(root, 'src/core/utils'), { recursive: true })
  await writeFile(resolve(root, 'src/views/Builtin.vue'), '<template>builtin</template>', 'utf-8')
  await writeFile(resolve(root, 'src/core/utils/build-release-view-modules.ts'), 'export const builtin = true\n', 'utf-8')
  await writeFile(resolve(root, 'src/core/utils/build-diagnostics-modules.ts'), 'export const diagnostics = true\n', 'utf-8')
  await writeFile(resolve(root, 'index.html'), '<div id="app"></div>', 'utf-8')
  return root
}

interface Deferred {
  promise: Promise<void>
  resolve: () => void
}

/**
 * 创建由测试控制结束时机的异步屏障。
 */
function createDeferred(): Deferred {
  let resolve = () => undefined
  const promise = new Promise<void>(done => {
    resolve = done
  })
  return { promise, resolve }
}
