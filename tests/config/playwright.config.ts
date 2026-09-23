/**
 * 文件功能：定义根仓平台级 E2E 测试配置，按 auth/smoke/visual-edit/ai/runtime-heavy 分层管理 project。
 *
 * 依据 docs/developer/testing/e2e-redesign.md §3.5/§3.6：
 * - project 语义由本配置显式定义，命令脚本通过 --project 选择范围，不依赖目录或标签的隐式约定；
 * - auth project 使用空 storageState，其余 project 复用 globalSetup 生成的登录状态；
 * - expect 默认 15s、action 默认 10s，异步边界在用例内显式放宽。
 */
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

import { STORAGE_STATE_PATH } from '../e2e/helpers/e2e-env'

const repoRoot = fileURLToPath(new URL('../../', import.meta.url))
const e2eSpecsDir = resolve(repoRoot, 'tests/e2e/specs')
const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const e2eReportDir = resolve(repoRoot, 'test-results/e2e/html-report')
const e2eArtifactDir = resolve(repoRoot, 'test-results/e2e/artifacts')
const storageStatePath = resolve(repoRoot, STORAGE_STATE_PATH)
const configuredWorkers = Number.parseInt(process.env.PLAYWRIGHT_WORKERS || '2', 10)
const e2eWorkers = Number.isInteger(configuredWorkers) && configuredWorkers > 0 ? configuredWorkers : 2

/** 空登录态：auth project 必须覆盖未登录重定向与登录成功，不能加载全局 storageState。 */
const emptyStorageState = { cookies: [], origins: [] }

export default defineConfig({
  testDir: e2eSpecsDir,
  globalSetup: resolve(repoRoot, 'tests/e2e/global-setup.ts'),
  timeout: 120_000,
  fullyParallel: false,
  // 固定为与 GitHub Actions 一致的 2 workers；调试时可通过 PLAYWRIGHT_WORKERS 覆盖。
  workers: e2eWorkers,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { outputFolder: e2eReportDir, open: 'never' }]],
  use: {
    baseURL,
    actionTimeout: 10_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  outputDir: e2eArtifactDir,
  projects: [
    {
      name: 'auth',
      testDir: resolve(e2eSpecsDir, 'auth'),
      use: {
        ...devices['Desktop Chrome'],
        storageState: emptyStorageState,
      },
    },
    {
      name: 'smoke',
      testDir: resolve(e2eSpecsDir, 'smoke'),
      use: {
        ...devices['Desktop Chrome'],
        storageState: storageStatePath,
      },
    },
    {
      name: 'visual-edit',
      testDir: resolve(e2eSpecsDir, 'visual-edit'),
      use: {
        ...devices['Desktop Chrome'],
        storageState: storageStatePath,
      },
    },
    {
      name: 'ai',
      testDir: resolve(e2eSpecsDir, 'ai'),
      use: {
        ...devices['Desktop Chrome'],
        storageState: storageStatePath,
      },
    },
    {
      name: 'runtime-heavy',
      testDir: resolve(e2eSpecsDir, 'runtime-heavy'),
      // 真实构建链路耗时较长，单独放宽用例级超时。
      timeout: 420_000,
      use: {
        ...devices['Desktop Chrome'],
        storageState: storageStatePath,
      },
    },
  ],
})
