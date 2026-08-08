/**
 * 文件功能：覆盖组件库页面打开与组件工作台可见的冒烟路径。
 */
import { expect, test } from '../../fixtures/base'

import { gotoWorkspaceHome } from '../../helpers/navigation'

test('组件库页面应可打开并展示组件工作台主区域', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await page.locator('[data-testid="workspace-dock-components"]').click()
  await expect(page.locator('[data-testid="components-view"]')).toBeVisible()
})
