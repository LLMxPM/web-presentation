/**
 * 文件功能：覆盖页面截图按钮、旧截图标记与详情页截图入口的冒烟路径。
 */
import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { openFirstProject, waitForWorkspaceHome } from '../helpers/navigation'

test('页面列表应暴露截图操作入口', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await openFirstProject(page)
  await expect(page.locator('[data-testid="batch-refresh-routed-page-screenshots"]')).toBeVisible()

  const firstCard = page.locator('[data-testid="page-card"]').first()
  await firstCard.hover()
  await expect(firstCard.locator('[data-testid="page-card-screenshot"]')).toBeVisible()
})
