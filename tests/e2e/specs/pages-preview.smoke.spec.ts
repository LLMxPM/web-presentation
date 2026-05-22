/**
 * 文件功能：覆盖平台 E2E 冒烟中的页面列表进入、页面详情打开与预览 iframe 可见主链路。
 */
import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { openFirstPage, openFirstProject, waitForWorkspaceHome } from '../helpers/navigation'

test('创建后的页面应可进入详情并展示预览 iframe', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await openFirstProject(page)
  await openFirstPage(page)
  await expect(page.locator('[data-testid="page-preview-frame"]')).toBeVisible()
})
