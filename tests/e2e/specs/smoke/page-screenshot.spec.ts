/**
 * 文件功能：覆盖页面截图按钮、旧截图标记与详情页截图入口的冒烟路径。
 */
import { expect, test } from '../../fixtures/base'

import { gotoWorkspaceHome, openSmokeProject } from '../../helpers/navigation'

test('页面列表应暴露截图操作入口', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await openSmokeProject(page)
  await expect(page.locator('[data-testid="batch-refresh-routed-page-screenshots"]')).toBeVisible()

  const firstCard = page.locator('[data-testid="page-card"]').first()
  await firstCard.hover()
  await expect(firstCard.locator('[data-testid="page-card-screenshot"]')).toBeVisible()
})
