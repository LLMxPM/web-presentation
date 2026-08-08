/**
 * 文件功能：覆盖项目构建入口弹窗可见性的冒烟路径；真实构建链路在 runtime-heavy project 覆盖。
 */
import { expect, test } from '../../fixtures/base'

import { gotoWorkspaceHome, openSmokeProject } from '../../helpers/navigation'

test('项目构建弹窗应可打开', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await openSmokeProject(page)
  await page.locator('[data-testid="project-build-open"]').click()
  await expect(page.locator('[data-testid="project-build-dialog"]')).toBeVisible()
})
