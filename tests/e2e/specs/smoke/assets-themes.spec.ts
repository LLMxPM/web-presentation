/**
 * 文件功能：覆盖资源库、主题与样式页面主区域可见性的冒烟路径。
 */
import { expect, test } from '../../fixtures/base'

import { gotoWorkspaceHome } from '../../helpers/navigation'

test('资源库与主题字体页应可打开', async ({ page }) => {
  await gotoWorkspaceHome(page)

  await page.locator('[data-testid="workspace-dock-assets"]').click()
  await expect(page.locator('[data-testid="assets-view"]')).toBeVisible()

  await page.locator('[data-testid="workspace-dock-themes"]').click()
  await expect(page.locator('[data-testid="themes-view"]')).toBeVisible()

  await page.locator('[data-testid="workspace-dock-styles"]').click()
  await expect(page.locator('[data-testid="workspace-styles-view"]')).toBeVisible()
})
