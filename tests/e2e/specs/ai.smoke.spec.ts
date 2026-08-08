/**
 * 文件功能：覆盖全局 AI 侧栏打开、确认态 shell 可见性的 deterministic 冒烟路径。
 */
import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { openFirstPage, openFirstProject, waitForWorkspaceHome } from '../helpers/navigation'

test('工作空间级内容助手无需进入项目即可打开，并可随页面导航继续使用', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await page.locator('[data-testid="agent-floating-trigger"]').click()
  const panel = page.locator('[data-testid="agent-sidebar-panel"]')
  await expect(panel).toBeVisible()
  await expect(panel).not.toContainText('需要先进入项目')

  await openFirstProject(page)
  await openFirstPage(page)
  await expect(panel).toBeVisible()
})
