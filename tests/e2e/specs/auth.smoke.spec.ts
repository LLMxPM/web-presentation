/**
 * 文件功能：覆盖平台 E2E 冒烟中的登录成功与未登录重定向主链路。
 */
import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { waitForWorkspaceHome } from '../helpers/navigation'

test('登录成功，未登录访问受保护页面会重定向到登录页', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)

  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
})
