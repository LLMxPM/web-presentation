/**
 * 文件功能：覆盖项目构建入口弹窗可见性的冒烟路径。
 */
import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { openFirstProject, waitForWorkspaceHome } from '../helpers/navigation'

test('项目构建弹窗应可打开', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await openFirstProject(page)
  await page.locator('[data-testid="project-build-open"]').click()
  await expect(page.locator('[data-testid="project-build-dialog"]')).toBeVisible()
})
