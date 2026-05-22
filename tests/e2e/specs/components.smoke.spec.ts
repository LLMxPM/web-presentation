/**
 * 文件功能：覆盖组件库页面打开与组件工作台可见的冒烟路径。
 */
import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { waitForWorkspaceHome } from '../helpers/navigation'

test('组件库页面应可打开并展示组件工作台主区域', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await page.locator('[data-testid="workspace-dock-components"]').click()
  await expect(page.locator('[data-testid="components-view"]')).toBeVisible()
})
