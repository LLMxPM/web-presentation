/**
 * 文件功能：正式用例开始前预热 Editor 冷启动编译与 Backend 鉴权链路，避免首批用例承担冷启动超时。
 */
import { chromium } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'

export default async function globalSetup() {
  const browser = await chromium.launch()
  try {
    const page = await browser.newPage()
    await page.goto(`${baseURL}/login`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-testid="login-username"]').fill('admin')
    await page.locator('[data-testid="login-password"]').fill('Admin123456')
    await page.locator('[data-testid="login-submit"]').click()
    await page.waitForURL(url => !/\/login$/.test(url.pathname), { timeout: 120_000 })
    await page.waitForSelector('[data-testid="workspace-project-list"]', { timeout: 120_000 })
    console.log('[e2e] Editor 与 Backend 预热完成')
  } finally {
    await browser.close()
  }
}
