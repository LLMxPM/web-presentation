/**
 * 文件功能：封装平台 E2E 登录动作，统一通过稳定选择器进入后台首页。
 */
import { expect, type Page } from '@playwright/test'

export async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.locator('[data-testid="login-username"]').fill('admin')
  await page.locator('[data-testid="login-password"]').fill('Admin123456')
  await page.locator('[data-testid="login-submit"]').click()
  await expect(page).not.toHaveURL(/\/login$/)
}
