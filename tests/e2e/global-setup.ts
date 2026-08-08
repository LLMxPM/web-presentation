/**
 * 文件功能：用例前校验 Backend 测试环境指纹、生成登录 storageState 并预热 Editor 冷启动编译。
 *
 * 依据 docs/developer/testing/e2e-redesign.md §3.2/§3.4：
 * - 先通过 /api/testing/e2e-readiness 确认 Backend 处于 E2E mock 环境且 smoke 数据就绪，
 *   前置数据缺失时快速失败并提示执行 pnpm run test:e2e:prepare，不进入业务页面后才失败；
 * - 登录一次并保存 storageState 供 auth 以外的 project 复用；
 * - 预热覆盖登录、工作空间首页与首个页面详情入口。
 */
import fs from 'node:fs'
import path from 'node:path'

import { chromium } from '@playwright/test'

import { E2E_BACKEND_URL, EXPECTED_SEED_VERSION, STORAGE_STATE_PATH } from './helpers/e2e-env'

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'

interface E2eReadiness {
  test_mode: string
  database_profile: string
  redis_profile: string
  seed_version: number
  scenario_version: string
  smoke_data_ready: boolean
}

/**
 * 校验 Backend 测试就绪指纹；任一指纹不匹配立即失败，避免把开发服务当作测试环境。
 */
async function assertBackendReadiness(): Promise<void> {
  const prepareHint = '请先执行 pnpm run test:e2e:prepare（reset + seed + ensure-services）。'
  let response: Response
  try {
    response = await fetch(`${E2E_BACKEND_URL}/api/testing/e2e-readiness`)
  } catch (error) {
    throw new Error(`Backend 就绪检查失败：无法连接 ${E2E_BACKEND_URL}（${String(error)}）。${prepareHint}`)
  }

  if (response.status === 404) {
    throw new Error(`Backend 未启用 AI_TEST_MODE=mock，测试就绪端点不可达。${prepareHint}`)
  }
  if (!response.ok) {
    throw new Error(`Backend 就绪检查失败：HTTP ${response.status}。${prepareHint}`)
  }

  const readiness = (await response.json()) as E2eReadiness
  const problems: string[] = []
  if (readiness.test_mode !== 'mock') problems.push(`test_mode=${readiness.test_mode}（期望 mock）`)
  if (readiness.database_profile !== 'e2e') problems.push(`database_profile=${readiness.database_profile}（期望 e2e）`)
  if (readiness.redis_profile !== 'e2e') problems.push(`redis_profile=${readiness.redis_profile}（期望 e2e）`)
  if (readiness.seed_version !== EXPECTED_SEED_VERSION) {
    problems.push(`seed_version=${readiness.seed_version}（期望 ${EXPECTED_SEED_VERSION}）`)
  }
  if (!readiness.smoke_data_ready) problems.push('smoke_data_ready=false（smoke 数据未播种或槽位未绑定）')

  if (problems.length) {
    throw new Error(`Backend 测试指纹不匹配：${problems.join('；')}。${prepareHint}`)
  }
  console.log(`[e2e] Backend 就绪指纹校验通过（scenario_version=${readiness.scenario_version}）`)
}

export default async function globalSetup() {
  await assertBackendReadiness()

  const browser = await chromium.launch()
  try {
    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto(`${baseURL}/login`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-testid="login-username"]').fill('admin')
    await page.locator('[data-testid="login-password"]').fill('Admin123456')
    await page.locator('[data-testid="login-submit"]').click()
    await page.waitForURL(url => !/\/login$/.test(url.pathname), { timeout: 120_000 })
    await page.waitForSelector('[data-testid="workspace-project-list"]', { timeout: 120_000 })

    // 预热首个页面详情入口，让后续用例不承担页面详情模块的冷编译成本。
    await page.locator('[data-testid="project-card"]').first().click()
    await page.waitForSelector('[data-testid="project-pages-view"]', { timeout: 120_000 })
    await page.locator('[data-testid="page-card"]').first().click()
    await page.waitForSelector('[data-testid="page-detail-view"]', { timeout: 120_000 })

    fs.mkdirSync(path.dirname(STORAGE_STATE_PATH), { recursive: true })
    await context.storageState({ path: STORAGE_STATE_PATH })
    console.log('[e2e] Editor 与 Backend 预热完成，storageState 已保存')
  } finally {
    await browser.close()
  }
}
