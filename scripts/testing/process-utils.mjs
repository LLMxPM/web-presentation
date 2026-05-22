/**
 * 文件功能：提供测试编排脚本共用的进程启动、轮询等待和退出处理工具。
 */
import { spawn } from 'node:child_process'

export async function waitForHttpReady(url, { timeoutMs = 60_000, intervalMs = 1_000 } = {}) {
  const deadline = Date.now() + timeoutMs
  let lastError = null
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { method: 'GET' })
      if (response.ok || response.status === 404) {
        return
      }
      lastError = new Error(`Unexpected status ${response.status} for ${url}`)
    } catch (error) {
      lastError = error
    }
    await sleep(intervalMs)
  }
  throw lastError || new Error(`Timed out while waiting for ${url}`)
}

export function spawnBackground(command, args, options = {}) {
  const child = spawn(command, args, {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...options,
  })
  child.on('exit', (code) => {
    if (code && code !== 0) {
      console.error(`[testing] process exited with code ${code}: ${command} ${args.join(' ')}`)
    }
  })
  return child
}

export function spawnPersistentBackground(command, args, options = {}) {
  const child = spawn(command, args, {
    stdio: 'ignore',
    shell: process.platform === 'win32',
    detached: process.platform !== 'win32',
    windowsHide: true,
    ...options,
  })
  child.unref()
  return child
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
