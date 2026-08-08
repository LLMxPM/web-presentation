/**
 * 文件功能：覆盖登录成功与未登录重定向主链路；auth project 使用空 storageState，不加载全局登录状态。
 */
import { expect, test } from '../../fixtures/base'

import { loginAsAdmin } from '../../helpers/auth'
import { waitForWorkspaceHome } from '../../helpers/navigation'

test('登录成功，未登录访问受保护页面会重定向到登录页', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)

  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
})
